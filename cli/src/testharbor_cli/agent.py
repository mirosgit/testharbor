"""`testcli agent`: run automated tests when someone presses "Run autotests" in TestHarbor.

The agent runs on the machine that has the tests. It polls TestHarbor for jobs of one
project, runs the command given on its own command line (never one sent by the server),
streams the output back, and uploads the report into the job's run.

For jobs limited to some cases, `--grep <regex>` is appended, matching the case ids
(C197, @C197, [C197]) in test titles or tags: Playwright's syntax.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .main import CliError, upload

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
PROGRESS_EVERY = 2.0  # seconds between log uploads / cancel checks


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


def case_grep(case_ids: list[int]) -> str:
    """Regex for test titles mentioning any of the cases: "C197 …", "@C197", "[C197]"."""
    ids = "|".join(str(int(i)) for i in case_ids)
    return f"(?<![A-Za-z0-9])C({ids})(?![0-9])"


def build_command(cfg: AgentConfig, case_ids: list[int]) -> list[str]:
    args = shlex.split(cfg.command, posix=os.name != "nt")
    if not args:
        raise CliError("--command is empty")
    exe = shutil.which(args[0], path=os.environ.get("PATH"))  # npx -> npx.cmd on Windows
    if exe:
        args[0] = exe
    if case_ids and cfg.grep_arg:
        args += [cfg.grep_arg, case_grep(case_ids)]
    return args


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

    report = cfg.report if cfg.report.is_absolute() else cfg.cwd / cfg.report
    try:
        report.unlink(missing_ok=True)  # never upload a report left over from an earlier run
        args = build_command(cfg, case_ids)
    except (OSError, CliError) as e:
        return finish("error", f"Could not prepare the run: {e}")

    env = {**os.environ, "TESTHARBOR_RUN_ID": str(run_id), "TESTHARBOR_JOB_ID": str(job_id),
           "TESTHARBOR_CASE_IDS": ",".join(map(str, case_ids)), "FORCE_COLOR": "0", "CI": os.environ.get("CI", "1")}
    out.add(f"$ {shlex.join(args)}\n")
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

    if not report.is_file():
        return finish("error", f"Tests exited with code {code} but no report was written to {cfg.report} "
                               "(is the JSON reporter configured?)", code)
    params = {
        "run_id": str(run_id),
        "report_url": cfg.report_url,
        "auto_create": "true" if cfg.auto_create else "",
        "branch": _git(cfg.cwd, "rev-parse", "--abbrev-ref", "HEAD"),
        "commit": _git(cfg.cwd, "rev-parse", "HEAD"),
    }
    try:
        result = upload(cfg.url, cfg.token, cfg.project, [report], params)
    except CliError as e:
        return finish("error", f"Upload failed: {e}", code)
    st = result.get("statuses", {})
    counts = ", ".join(f"{v} {k}" for k, v in sorted(st.items())) or "no results"
    summary = (f"{result.get('total', 0)} tests ({counts}); matched {result.get('matched', 0)}, "
               f"created {result.get('created', 0)}, unmatched {len(result.get('unmatched', []))}")
    return finish("finished", summary, code)


def run_agent(cfg: AgentConfig, log=print) -> int:  # type: ignore[no-untyped-def]
    api = Api(cfg)
    log(f"testcli agent \"{cfg.name}\" waiting for jobs of project {cfg.project} at {cfg.url}")
    log(f"  runs: {cfg.command}   in {cfg.cwd}   report: {cfg.report}")
    def on_sigterm(*_: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, on_sigterm)
    failures = 0
    try:
        while True:
            try:
                code, job = api.call("POST", f"/api/projects/{cfg.project}/automation/claim", {"agent": cfg.name})
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
                continue
            time.sleep(cfg.poll)
    except KeyboardInterrupt:
        log("agent stopped")
        return 130
