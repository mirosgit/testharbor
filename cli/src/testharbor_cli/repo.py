"""Server agents: `testcli agent --repo URL` runs a git branch of a repository in a clean checkout.

For every job the agent fetches the repository, checks the job's branch (or the default one) out
into a fresh worktree, copies the tests' secrets file (`--env-file`) to its `.env`, runs `setup`
from the branch's testharbor.toml (e.g. `uv sync`), then runs the tests like a local agent and
removes the worktree. It tells TestHarbor the repository's branches, so people pick one.

Credentials: for HTTPS, TESTHARBOR_GIT_TOKEN (and TESTHARBOR_GIT_USER, default `x-token-auth`
as Bitbucket and GitLab access tokens want) are given to git through GIT_ASKPASS, so they are never
part of a URL, a log or `git remote -v`. For SSH, the machine's key is used.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .main import CliError

BRANCH = re.compile(r"^(?!-)(?!.*\.\.)[A-Za-z0-9._/@+-]{1,255}$")
FETCH_EVERY = 60.0  # seconds between refreshing the list of branches while idle
_ASKPASS = """#!/bin/sh
case "$1" in
  Username*) printf '%s\\n' "${TESTHARBOR_GIT_USER:-x-token-auth}" ;;
  *) printf '%s\\n' "$TESTHARBOR_GIT_TOKEN" ;;
esac
"""


def display_url(url: str) -> str:
    """The repository without credentials or scheme: `bitbucket.org/team/qa-tests`."""
    url = re.sub(r"^[a-z+]+://", "", url)
    url = re.sub(r"^[^@/]+@", "", url)
    return re.sub(r"\.git$", "", url.replace(":", "/", 1) if re.match(r"^[^/]+:[^/]", url) else url)


class Repo:
    """A clone of the repository (no checkout of its own) and the worktrees made from it."""

    def __init__(self, url: str, workdir: Path) -> None:
        self.url = url
        self.workdir = workdir
        self.clone = workdir / "clone"
        self.runs = workdir / "runs"
        self.env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
        if os.environ.get("TESTHARBOR_GIT_TOKEN"):
            workdir.mkdir(parents=True, exist_ok=True)
            askpass = workdir / "askpass.sh"
            askpass.write_text(_ASKPASS)
            askpass.chmod(0o700)
            self.env["GIT_ASKPASS"] = str(askpass)

    def git(self, *args: str, cwd: Path | None = None, timeout: float = 900) -> str:
        try:
            done = subprocess.run(["git", *args], cwd=cwd or self.clone, env=self.env, capture_output=True,
                                  text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as e:
            raise CliError(f"git {args[0]}: {e}") from e
        if done.returncode != 0:
            secret = os.environ.get("TESTHARBOR_GIT_TOKEN")
            err = (done.stderr or done.stdout).strip()
            if secret:
                err = err.replace(secret, "***")
            raise CliError(f"git {args[0]} failed: {err[-1500:]}")
        return done.stdout.strip()

    def sync(self) -> None:
        """Clone on first use, then fetch: the branches as they are now."""
        if not (self.clone / ".git").exists():
            self.workdir.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(self.clone, ignore_errors=True)
            self.git("clone", "--no-checkout", "--", self.url, str(self.clone), cwd=self.workdir)
        else:
            self.git("remote", "set-url", "origin", self.url)
            self.git("fetch", "--prune", "--force", "origin", "+refs/heads/*:refs/remotes/origin/*")
        try:
            self.git("remote", "set-head", "origin", "--auto")
        except CliError:
            pass

    def branches(self) -> list[str]:
        """Remote branches, most recently changed first."""
        out = self.git("for-each-ref", "--sort=-committerdate", "--format=%(refname:lstrip=3)", "refs/remotes/origin")
        return [b for b in out.splitlines() if b and b != "HEAD"][:2000]

    def default_branch(self) -> str:
        try:
            return self.git("symbolic-ref", "--short", "refs/remotes/origin/HEAD").split("/", 1)[1]
        except (CliError, IndexError):
            names = self.branches()
            return next((b for b in ("main", "master", "develop") if b in names), names[0] if names else "main")

    def checkout(self, branch: str, name: str) -> tuple[Path, str]:
        """A fresh worktree of origin/<branch> at its latest commit."""
        if not BRANCH.match(branch) or branch not in self.branches():
            raise CliError(f"branch {branch!r} is not in {display_url(self.url)} (pushed?)")
        path = self.runs / name
        self.remove(path)
        self.runs.mkdir(parents=True, exist_ok=True)
        self.git("worktree", "add", "--detach", "--force", str(path), f"refs/remotes/origin/{branch}")
        return path, self.git("rev-parse", "HEAD", cwd=path)

    def remove(self, path: Path) -> None:
        if path.exists():
            try:
                self.git("worktree", "remove", "--force", str(path))
            except CliError:
                shutil.rmtree(path, ignore_errors=True)
        try:
            self.git("worktree", "prune")
        except CliError:
            pass


@dataclass
class RepoAgent:
    url: str  # TestHarbor
    token: str
    project: int
    repo: str  # git URL
    workdir: Path
    name: str
    env_file: Path | None = None  # the tests' secrets, copied to .env of every checkout
    secret_files: Path | None = None  # a folder copied into every checkout as is (config/credentials.ini…)
    branch: str = ""  # default branch (empty: the repository's)
    subdir: str = ""  # folder of testharbor.toml in the repository (empty: found)
    poll: float = 3.0
    once: bool = False
    info: dict[str, Any] = field(default_factory=dict)
    reports_url: str = ""  # how people reach the runner's reports (e.g. http://testharbor.example.com:9323)
    reports_port: int = 9323


def run_setup(commands: list[str], cwd: Path, out) -> None:  # type: ignore[no-untyped-def]
    """setup commands of the branch's testharbor.toml, output into the job log."""
    import shlex

    env = {k: v for k, v in os.environ.items() if k not in ("TESTHARBOR_TOKEN", "TESTHARBOR_GIT_TOKEN")}
    for command in commands:
        args = shlex.split(command)
        if args and (exe := shutil.which(args[0])):
            args[0] = exe
        out(f"$ {command}\n")
        try:
            done = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=1800)
        except (OSError, subprocess.SubprocessError) as e:
            raise CliError(f"setup `{command}` failed: {e}") from e
        out("\n".join((done.stdout + done.stderr).strip().splitlines()[-40:]) + "\n")
        if done.returncode != 0:
            raise CliError(f"setup `{command}` exited with code {done.returncode}")


def find_branch_config(path: Path, subdir: str = "") -> Path:
    """testharbor.toml of a checkout: in `subdir` if given, else at the root or (if only one) deeper down."""
    from .config import CONFIG_NAMES

    base = path / subdir if subdir else path
    for name in CONFIG_NAMES:
        if (base / name).is_file():
            return base / name
    if not subdir:
        found = [p for name in CONFIG_NAMES for p in path.glob(f"*/{name}")]
        found += [p for name in CONFIG_NAMES for p in path.glob(f"*/*/{name}")]
        found = [p for p in found if "node_modules" not in p.parts]
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            raise CliError("several testharbor.toml in this branch: choose one with --repo-path "
                           + ", ".join(str(p.parent.relative_to(path)) for p in found))
    raise CliError(f"no testharbor.toml in {subdir or 'this branch'}: commit one (`testcli init`)")


def _prepare_checkout(ra: RepoAgent, repo: Repo, branch: str, slot: str, out) -> Any:  # type: ignore[no-untyped-def]
    """Check a branch out, copy the secrets, run setup and prepare: an AgentConfig for its tests."""
    from .agent import AgentConfig, load_options
    from .config import agent_kwargs, load_config, run_prepare

    path, commit = repo.checkout(branch, slot)
    out(f"Checked out {branch} at {commit[:10]} of {display_url(ra.repo)}\n")
    conf_path = find_branch_config(path, ra.subdir)
    root = conf_path.parent
    if ra.env_file is not None:
        shutil.copyfile(ra.env_file, root / ".env")
        (root / ".env").chmod(0o600)
    if ra.secret_files is not None and ra.secret_files.is_dir():
        for src in ra.secret_files.rglob("*"):
            if src.is_file():
                dest = root / src.relative_to(ra.secret_files)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
                dest.chmod(0o600)
    conf = load_config(conf_path)
    if conf.get("secrets"):
        out("secrets: not run on a server (they are for local agents); the tests get the server's tests.env\n")
    run_setup(conf.get("setup", []), root, out)
    cfg = AgentConfig(url=ra.url, token=ra.token, project=ra.project, name=ra.name, poll=ra.poll, once=ra.once,
                      branch_name=branch, **agent_kwargs(conf, root, read_options=False))
    if cfg.prepare:
        out(f"$ {cfg.prepare}\n")
        run_prepare(cfg.prepare, root, lambda *_: None)
    if cfg.options_file is not None:
        cfg.options = load_options(root / cfg.options_file)
    return cfg


def run_repo_agent(ra: RepoAgent, log=print) -> int:  # type: ignore[no-untyped-def]
    import signal

    from .agent import Api, AgentConfig, run_job, select_mode, upload_catalog

    api = Api(AgentConfig(url=ra.url, token=ra.token, project=ra.project, command="", report=Path(".")))
    repo = Repo(ra.repo, ra.workdir)
    where = display_url(ra.repo)
    log(f"testcli agent \"{ra.name}\" (server) for project {ra.project} at {ra.url}: runs branches of {where}")

    def on_sigterm(*_: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, on_sigterm)
    try:
        repo.sync()
    except CliError as e:
        log(f"  {e}")
        return 1
    default = ra.branch or repo.default_branch()
    options: list[dict[str, Any]] = []

    def describe() -> dict[str, Any]:
        return {"mode": "repo", "repo": where, "default_branch": default, "branches": repo.branches()}

    def refresh_default() -> None:
        """Options and catalog come from the default branch."""
        nonlocal options
        try:
            cfg = _prepare_checkout(ra, repo, default, "catalog", lambda text: None)
            if cfg.catalog is not None:
                upload_catalog(cfg, api, log)
            options = cfg.options
        except CliError as e:
            log(f"  {default}: {e}")
        finally:
            repo.remove(repo.runs / "catalog")

    from .serve import keep_report, start

    reports = ra.workdir / "reports"
    port = start(reports, ra.reports_port, host="0.0.0.0")
    reports_base = (ra.reports_url or f"http://localhost:{port}").rstrip("/")
    log(f"  reports: {reports_base}/ (port {port})")
    refresh_default()
    info = describe()
    log(f"  default branch {default}; {len(info['branches'])} branches")
    last_fetch = time.monotonic()
    failures = 0
    try:
        while True:
            if time.monotonic() - last_fetch > FETCH_EVERY:
                try:
                    repo.sync()
                    info = describe()
                except CliError as e:
                    log(f"  {e}")
                last_fetch = time.monotonic()
            try:
                code, job = api.call("POST", f"/api/projects/{ra.project}/automation/claim",
                                     {"agent": ra.name, "options": options, "info": info})
                failures = 0
            except CliError as e:
                failures += 1
                if failures in (1, 10) or failures % 100 == 0:
                    log(f"  {e}; retrying…")
                if "HTTP 401" in str(e) or "HTTP 404" in str(e):
                    return 1
                time.sleep(min(ra.poll * failures, 30))
                continue
            if not (code == 200 and job):
                time.sleep(ra.poll)
                continue
            branch = job.get("branch") or default
            slot = f"job-{job['id']}"
            lines: list[str] = []

            def out(text: str) -> None:
                lines.append(text)
                try:
                    api.call("POST", f"/api/automation/jobs/{job['id']}/progress", {"log": text})
                except CliError:
                    pass

            try:
                out(f"Fetching {where}…\n")
                repo.sync()
                cfg = _prepare_checkout(ra, repo, branch, slot, out)
                if select_mode(cfg) == "args" and job.get("case_ids"):
                    if not job.get("automation_keys"):
                        raise CliError("none of the selected cases is linked to a test: sync the autotests first")
                    # Only tests that exist in this checkout may be passed to the command (see build_command).
                    from .collect import build_catalog
                    cfg.known_keys = {str(t["key"]) for t in build_catalog(cfg.framework, cfg.command, cfg.cwd)}
                cfg.catalog = None  # the catalog follows the default branch only
                page = cfg.report_html.replace("{job_id}", str(job["id"])) if cfg.report_html else ""
                if page and not cfg.report_url:
                    cfg.report_url = f"{reports_base}/{slot}/{Path(page).name}"
                run_job(cfg, api, job, log)
                if page:
                    keep_report(cfg.cwd / page, reports, slot)  # the checkout is removed below
            except (CliError, OSError) as e:
                try:
                    api.call("POST", f"/api/automation/jobs/{job['id']}/finish",
                             {"status": "error", "message": f"{branch}: {e}"[:5000], "log": ""})
                except CliError:
                    pass
                log(f"  ✖ job #{job['id']}: {e}")
            finally:
                repo.remove(repo.runs / slot)
            if ra.once:
                return 0
            if branch == default:
                refresh_default()
    except KeyboardInterrupt:
        log("agent stopped")
        return 130
