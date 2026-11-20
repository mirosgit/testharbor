"""`testcli agent`: run automated tests when someone presses "Run autotests" in TestHarbor.

The agent runs on the machine that has the tests. It polls TestHarbor for jobs of one
project, runs the command given on its own command line (never one sent by the server),
streams the output back, and uploads the report into the job's run.

For jobs limited to some cases, `--grep <regex>` is appended, matching the case ids
(C197, @C197, [C197]) in test titles or tags: Playwright's syntax. The ids are also in
TESTHARBOR_CASE_IDS, for commands that select tests themselves (`--grep-arg ""`).

Run options (`--options FILE`): the agent tells TestHarbor which environment variables of its
command a person may set and to which values (an environment, roles, a browser). A job carries the
chosen values; the agent checks each against its own file and sets the variables. Anything
else is refused, so the server can only pick from what the agent offers.

Catalog (`--catalog FILE`): the tests the agent can run, uploaded when it starts. People sync it
into cases in TestHarbor after a preview. A job for selected cases then also gets their automation
keys: the command finds both lists in the JSON file named by TESTHARBOR_SELECTION
({"case_ids": [...], "automation_keys": [...]}).

`--report` and `--report-url` may contain `{job_id}`; `--report` may be a glob
(`reports/t{job_id}/*/junit.xml`): every matching file written during the job is uploaded.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .main import CliError, upload

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
PROGRESS_EVERY = 2.0  # seconds between log uploads / cancel checks
OPTION_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
OPTION_TYPES = ("choice", "multi", "bool")
# Variables a run option may not set: they change how programs start, or belong to the agent.
RESERVED_ENV = re.compile(
    r"^(PATH|HOME|SHELL|IFS|BASH_ENV|CDPATH|LD_\w*|DYLD_\w*|PYTHON\w*|NODE_OPTIONS|NODE_PATH|"
    r"JAVA_TOOL_OPTIONS|PERL5\w*|RUBYOPT|GIT_\w*|TESTHARBOR_\w*)$"
)
# Never handed to the tests: the agent's own credentials.
PRIVATE_ENV = ("TESTHARBOR_TOKEN", "TESTHARBOR_GIT_TOKEN")


@dataclass
class AgentConfig:
    url: str
    token: str
    project: int
    command: str
    report: Path
    cwd: Path = field(default_factory=Path.cwd)
    name: str = field(default_factory=socket.gethostname)
    report_url: str = ""
    auto_create: bool = False
    grep_arg: str = "--grep"
    poll: float = 3.0
    once: bool = False
    options: list[dict[str, Any]] = field(default_factory=list)  # from --options, see load_options()
    options_file: Path | None = None  # re-read after `prepare`
    catalog: Path | str | None = None  # a JSON file, or "auto" (built in for playwright / pytest)
    framework: str = "custom"  # playwright | pytest | custom (testharbor.toml)
    # How selected tests reach the command: grep (--grep regex), args (node ids), env/none (only
    # TESTHARBOR_SELECTION). Empty: grep when grep_arg is set, else none (older command lines).
    select: str = ""
    prepare: str = ""  # runs before options and catalog are (re)read
    extra_env: dict[str, str] = field(default_factory=dict)
    info: dict[str, Any] = field(default_factory=dict)  # shown in TestHarbor: folder, branch, changes
    branch_name: str = ""  # a server agent's checkout is detached: the branch the job asked for


def case_grep(case_ids: list[int]) -> str:
    """Regex for test titles mentioning any of the cases: "C197 …", "@C197", "[C197]"."""
    ids = "|".join(str(int(i)) for i in case_ids)
    return f"(?<![A-Za-z0-9])C({ids})(?![0-9])"


def select_mode(cfg: AgentConfig) -> str:
    return cfg.select or ("grep" if cfg.grep_arg else "none")


def build_command(cfg: AgentConfig, case_ids: list[int], keys: list[str] | None = None) -> list[str]:
    from .collect import grep_for_keys, pytest_args

    args = shlex.split(cfg.command, posix=os.name != "nt")
    if not args:
        raise CliError("--command is empty")
    exe = shutil.which(args[0], path=os.environ.get("PATH"))  # npx -> npx.cmd on Windows
    if exe:
        args[0] = exe
    keys = keys or []
    mode = select_mode(cfg)
    if mode == "grep" and (case_ids or keys):
        args += [cfg.grep_arg or "--grep", grep_for_keys(keys, case_ids) if keys else case_grep(case_ids)]
    elif mode == "args" and case_ids:
        if not keys:
            raise CliError("none of the selected cases is linked to a test (no automation key): "
                           "sync the autotests in TestHarbor first")
        args += pytest_args(keys)
    return args


def local_info(cfg: AgentConfig) -> dict[str, Any]:
    """Where this agent runs tests from: shown next to its name in TestHarbor."""
    home = str(Path.home())
    folder = str(cfg.cwd)
    if folder == home or folder.startswith(home + os.sep):
        folder = "~" + folder[len(home):]
    info: dict[str, Any] = {"mode": "local", "folder": folder, "framework": cfg.framework}
    branch = _git(cfg.cwd, "rev-parse", "--abbrev-ref", "HEAD")
    if branch:
        info["branch"] = branch
        info["commit"] = _git(cfg.cwd, "rev-parse", "--short", "HEAD")
        info["dirty"] = bool(_git(cfg.cwd, "status", "--porcelain", "--untracked-files=no"))
    return info


def load_options(path: Path) -> list[dict[str, Any]]:
    """Read and check an --options file: {"options": [{name, label, type, choices, default, hint}]}.

    `type` is "choice" (one of `choices`), "multi" (any of them, passed space-separated) or
    "bool" (passed as 1 / 0). A choice is {"value", "label"} or a plain string.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise CliError(f"--options {path}: {e.strerror or e}") from e
    except ValueError as e:
        raise CliError(f"--options {path}: not valid JSON ({e})") from e
    raw = data.get("options") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raise CliError(f'--options {path}: expected {{"options": [...]}}')
    options: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise CliError(f"--options {path}: every option must be an object")
        name, kind = item.get("name"), item.get("type")
        if not isinstance(name, str) or not OPTION_NAME.match(name) or RESERVED_ENV.match(name):
            raise CliError(f"--options {path}: {name!r} cannot be a run option (an UPPER_CASE variable name, "
                           "not PATH, LD_*, PYTHON*, TESTHARBOR_* …)")
        if kind not in OPTION_TYPES:
            raise CliError(f"--options {path}: {name}: type must be one of {', '.join(OPTION_TYPES)}")
        choices = []
        for c in item.get("choices") or []:
            value, label = (c, c) if isinstance(c, str) else (c.get("value"), c.get("label")) if isinstance(c, dict) else (None, None)
            if not isinstance(value, str):
                raise CliError(f"--options {path}: {name}: every choice needs a string value")
            choices.append({"value": value, "label": label if isinstance(label, str) and label else value})
        if kind != "bool" and not choices:
            raise CliError(f"--options {path}: {name}: no choices")
        option: dict[str, Any] = {"name": name, "label": str(item.get("label") or name), "type": kind,
                                  "choices": choices}
        if item.get("hint"):
            option["hint"] = str(item["hint"])
        default = item.get("default")
        option["default"] = _check_value(option, default) if default is not None else _fallback(option)
        options.append(option)
    if len({o["name"] for o in options}) != len(options):
        raise CliError(f"--options {path}: an option is listed twice")
    return options


def _fallback(option: dict[str, Any]) -> str | bool | list[str]:
    return {"bool": False, "multi": []}.get(option["type"], option["choices"][0]["value"] if option["choices"] else "")


def _check_value(option: dict[str, Any], value: object) -> str | bool | list[str]:
    name, kind = option["name"], option["type"]
    allowed = {c["value"] for c in option["choices"]}
    if kind == "bool":
        if not isinstance(value, bool):
            raise CliError(f"Run option {name} must be true or false")
        return value
    if kind == "multi":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise CliError(f"Run option {name} must be a list")
        bad = [v for v in value if v not in allowed]
        if bad:
            raise CliError(f"Run option {name}: {bad[0]!r} is not offered by this agent")
        return list(dict.fromkeys(value))
    if not isinstance(value, str) or value not in allowed:
        raise CliError(f"Run option {name}: {value!r} is not offered by this agent")
    return value


def option_env(options: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, str]:
    """The environment variables of a job: every offered option, set to the job's value or its default."""
    offered = {o["name"] for o in options}
    unknown = sorted(set(params) - offered)
    if unknown:
        raise CliError(f"Run option {unknown[0]} is not offered by this agent"
                       + ("" if offered else " (it was started without --options)"))
    env: dict[str, str] = {}
    for o in options:
        value = _check_value(o, params[o["name"]]) if o["name"] in params else o["default"]
        env[o["name"]] = ("1" if value else "0") if isinstance(value, bool) else (
            " ".join(value) if isinstance(value, list) else value)
    return env


def report_files(pattern: str, cwd: Path, since: float) -> list[Path]:
    """The report(s) of a job: a path, or every file matching a glob that was written during the job."""
    full = pattern if Path(pattern).is_absolute() else str(cwd / pattern)
    if not glob.has_magic(full):
        return [Path(full)] if Path(full).is_file() else []
    found = []
    for m in sorted(glob.glob(full, recursive=True)):
        p = Path(m)
        try:
            if p.is_file() and p.stat().st_mtime >= since - 1:
                found.append(p)
        except OSError:
            continue
    return found


def _git(cwd: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


class Api:
    def __init__(self, cfg: AgentConfig):
        self.base = cfg.url.rstrip("/")
        self.token = cfg.token

    def call(self, method: str, path: str, body: dict | None = None, timeout: float = 30) -> tuple[int, dict | None]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.base}{path}", data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"testharbor-agent/{__version__}",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            try:
                detail = json.loads(detail).get("detail", detail)
            except (ValueError, AttributeError):
                pass
            hint = " (check TESTHARBOR_TOKEN)" if e.code == 401 else ""
            raise CliError(f"HTTP {e.code}: {detail}{hint}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise CliError(f"Cannot reach {self.base}: {getattr(e, 'reason', e)}") from e


class _Output:
    """Collects the process output; flushed to the server every few seconds."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buf: list[str] = []

    def add(self, text: str) -> None:
        with self._lock:
            self._buf.append(text)

    def take(self) -> str:
        with self._lock:
            out, self._buf = "".join(self._buf), []
        return out


def run_job(cfg: AgentConfig, api: Api, job: dict, log=print) -> str:  # type: ignore[no-untyped-def]
    """Run one job to the end. Returns the status sent to the server."""
    job_id, run_id, case_ids = job["id"], job["run_id"], job.get("case_ids") or []
    scope = ", ".join(f"C{i}" for i in case_ids) if case_ids else "all tests"
    log(f"▶ job #{job_id} → run R{run_id} ({scope})")
    out = _Output()

    def finish(status: str, message: str, exit_code: int | None = None) -> str:
        try:
            api.call("POST", f"/api/automation/jobs/{job_id}/finish",
                     {"status": status, "exit_code": exit_code, "message": message[:5000], "log": out.take()})
        except CliError as e:
            log(f"  could not report the result: {e}")
        log(f"  {'✔' if status == 'finished' else '✖'} {message}")
        return status

    pattern = str(cfg.report).replace("{job_id}", str(job_id))
    report_url = cfg.report_url.replace("{job_id}", str(job_id))
    started = time.time()
    try:
        if not glob.has_magic(pattern):
            # never upload a report left over from an earlier run
            (Path(pattern) if Path(pattern).is_absolute() else cfg.cwd / pattern).unlink(missing_ok=True)
        options = option_env(cfg.options, job.get("params") or {})
        args = build_command(cfg, case_ids, job.get("automation_keys") or [])
    except (OSError, CliError) as e:
        return finish("error", f"Could not prepare the run: {e}")

    env = {k: v for k, v in os.environ.items() if k not in PRIVATE_ENV}
    env.update(cfg.extra_env)
    env.update(options)
    selection_dir = tempfile.TemporaryDirectory(prefix="testharbor-")
    selection = Path(selection_dir.name) / "selection.json"
    selection.write_text(json.dumps({"case_ids": case_ids, "automation_keys": job.get("automation_keys") or []}),
                         encoding="utf-8")
    env.update({"TESTHARBOR_RUN_ID": str(run_id), "TESTHARBOR_JOB_ID": str(job_id),
                "TESTHARBOR_CASE_IDS": ",".join(map(str, case_ids)), "TESTHARBOR_SELECTION": str(selection),
                "FORCE_COLOR": "0", "CI": os.environ.get("CI", "1")})
    if options:
        out.add("".join(f"{k}={shlex.quote(v)} " for k, v in options.items()))
    out.add(f"$ {shlex.join(args)}\n")
    try:
        return _execute(cfg, api, job, args, env, out, finish, pattern, report_url, started, log)
    finally:
        selection_dir.cleanup()


def _execute(cfg: AgentConfig, api: Api, job: dict, args: list[str], env: dict[str, str], out: _Output,  # type: ignore[no-untyped-def]
             finish, pattern: str, report_url: str, started: float, log) -> str:
    job_id, run_id = job["id"], job["run_id"]
    try:
        proc = subprocess.Popen(args, cwd=cfg.cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", bufsize=1)
    except OSError as e:
        return finish("error", f"Could not start {args[0]!r}: {e}")

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write("  " + line)
            out.add(_ANSI.sub("", line))

    def stop() -> None:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    cancelled = False
    try:
        while proc.poll() is None:
            time.sleep(PROGRESS_EVERY)
            try:
                _, ctl = api.call("POST", f"/api/automation/jobs/{job_id}/progress", {"log": out.take()})
            except CliError as e:
                log(f"  (progress not sent: {e})")
                continue
            if ctl and ctl.get("cancelled") and not cancelled:
                cancelled = True
                log("  cancelled in TestHarbor, stopping the tests…")
                stop()
    except KeyboardInterrupt:
        stop()
        finish("error", "The agent was stopped while the tests were running", proc.poll())
        raise
    reader.join(timeout=5)
    code = proc.wait()
    if cancelled:
        return finish("error", "Cancelled", code)

    reports = report_files(pattern, cfg.cwd, started)
    if not reports:
        return finish("error", f"Tests exited with code {code} but no report was written to {pattern} "
                               "(see the output: nothing selected to run, or no reporter configured)", code)
    params = {
        "run_id": str(run_id),
        "report_url": report_url,
        "auto_create": "true" if cfg.auto_create else "",
        "branch": cfg.branch_name or _git(cfg.cwd, "rev-parse", "--abbrev-ref", "HEAD"),
        "commit": _git(cfg.cwd, "rev-parse", "HEAD"),
    }
    try:
        result = upload(cfg.url, cfg.token, cfg.project, reports, params)
    except CliError as e:
        return finish("error", f"Upload failed: {e}", code)
    st = result.get("statuses", {})
    counts = ", ".join(f"{v} {k}" for k, v in sorted(st.items())) or "no results"
    summary = (f"{result.get('total', 0)} tests ({counts}); matched {result.get('matched', 0)}, "
               f"created {result.get('created', 0)}, unmatched {len(result.get('unmatched', []))}")
    return finish("finished", summary, code)


def upload_catalog(cfg: AgentConfig, api: Api, log=print) -> bool:  # type: ignore[no-untyped-def]
    """Send the catalog to TestHarbor; nothing changes there until someone applies the sync."""
    from .collect import build_catalog

    assert cfg.catalog is not None
    try:
        if cfg.catalog == "auto":
            tests = build_catalog(cfg.framework, cfg.command, cfg.cwd)
        else:
            path = Path(cfg.catalog)
            data = json.loads((path if path.is_absolute() else cfg.cwd / path).read_text(encoding="utf-8"))
            tests = data["tests"] if isinstance(data, dict) else data
        _, preview = api.call("PUT", f"/api/projects/{cfg.project}/automation/catalog",
                              {"agent": cfg.name, "tests": tests}, timeout=120)
    except (OSError, ValueError, KeyError, TypeError) as e:
        log(f"  catalog not sent: cannot read {cfg.catalog} ({e})")
        return False
    except CliError as e:
        log(f"  catalog not sent: {e}")
        return False
    counts = (preview or {}).get("counts", {})
    todo = {k: v for k, v in counts.items() if k != "unchanged" and v}
    summary = ", ".join(f"{v} {k}" for k, v in todo.items()) or "everything in sync"
    log(f"  catalog: {len(tests)} tests sent ({summary})"
        + (" — review it in TestHarbor: Autotests › Sync autotests" if todo else ""))
    return True


def refresh(cfg: AgentConfig, api: Api, log=print) -> None:  # type: ignore[no-untyped-def]
    """Re-read what may have changed in the folder: prepare, options, catalog, branch."""
    from .config import run_prepare

    if cfg.prepare:
        try:
            run_prepare(cfg.prepare, cfg.cwd, log)
        except CliError as e:
            log(f"  {e}")
    if cfg.options_file is not None:
        try:
            path = cfg.options_file if cfg.options_file.is_absolute() else cfg.cwd / cfg.options_file
            cfg.options = load_options(path)
        except CliError as e:
            log(f"  options not reloaded: {e}")
    cfg.info = local_info(cfg)
    if cfg.catalog is not None:
        upload_catalog(cfg, api, log)


def run_agent(cfg: AgentConfig, log=print) -> int:  # type: ignore[no-untyped-def]
    api = Api(cfg)
    log(f"testcli agent \"{cfg.name}\" waiting for jobs of project {cfg.project} at {cfg.url}")
    log(f"  runs: {cfg.command}   in {cfg.cwd}   report: {cfg.report}")
    if cfg.options:
        log(f"  run options: {', '.join(o['name'] for o in cfg.options)}")
    def on_sigterm(*_: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, on_sigterm)
    refresh(cfg, api, log)
    if cfg.info.get("branch"):
        log(f"  branch {cfg.info['branch']}" + (" (with uncommitted changes)" if cfg.info.get("dirty") else ""))
    failures = 0
    try:
        while True:
            try:
                code, job = api.call("POST", f"/api/projects/{cfg.project}/automation/claim",
                                     {"agent": cfg.name, "options": cfg.options, "info": cfg.info})
                failures = 0
            except CliError as e:
                failures += 1
                if failures in (1, 10) or failures % 100 == 0:
                    log(f"  {e}; retrying…")
                if "HTTP 401" in str(e) or "HTTP 404" in str(e):
                    return 1
                time.sleep(min(cfg.poll * failures, 30))
                continue
            if code == 200 and job:
                run_job(cfg, api, job, log)
                if cfg.once:
                    return 0
                refresh(cfg, api, log)  # the tests may have changed meanwhile (a local folder)
                continue
            time.sleep(cfg.poll)
    except KeyboardInterrupt:
        log("agent stopped")
        return 130
