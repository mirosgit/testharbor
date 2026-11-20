"""testharbor.toml: how `testcli agent` runs the tests of a repository.

    # testharbor.toml (next to the tests; `testcli init` writes one)
    url = "https://testharbor.example.com"
    project = 38
    framework = "playwright"        # playwright | pytest | custom: the defaults below
    # command = "npx playwright test --reporter=list,json,html"
    # report = "reports/results.json"
    # select = "grep"               # grep | args | env | none: how selected tests reach the command
    # catalog = "auto"              # auto (built in for playwright/pytest) | a JSON file | "" (none)
    # options = "testharbor-options.json"
    # prepare = "..."               # runs before reading options/catalog (e.g. a generator)
    # setup = ["uv sync --locked"]  # server agents only: after checking out a branch, before anything else
    # secrets = "./get-secrets.sh"  # local agents only: runs in your terminal when the agent starts (an MFA
    #                               # code, a vault login…); server agents get secrets from their tests.env

The token is never in this file: TESTHARBOR_TOKEN comes from the environment or from the `.env`
next to the config (only TESTHARBOR_* lines are read from it). Command-line flags win over the
file, the file wins over TESTHARBOR_URL / TESTHARBOR_PROJECT.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .main import CliError

CONFIG_NAMES = ("testharbor.toml", "testharbor.json")
FRAMEWORKS = ("playwright", "pytest", "custom")
SELECT_MODES = ("grep", "args", "env", "none")
KEYS = {
    "url", "project", "framework", "command", "report", "report_url", "select", "grep_arg", "catalog",
    "options", "prepare", "setup", "secrets", "auto_create", "name", "poll", "env",
}

# What each framework gets unless the config says otherwise.
PRESETS: dict[str, dict[str, Any]] = {
    "playwright": {
        "command": "npx playwright test --reporter=list,json,html",
        "report": "reports/results.json",
        "select": "grep",
        "catalog": "auto",
        # The JSON reporter writes to stdout unless told where; the HTML report must not open a browser.
        "env": {"PLAYWRIGHT_JSON_OUTPUT_NAME": "reports/results.json", "PLAYWRIGHT_HTML_OPEN": "never"},
    },
    "pytest": {
        "command": "python -m pytest --junitxml=reports/junit.xml",
        "report": "reports/junit.xml",
        "select": "args",
        "catalog": "auto",
        "env": {},
    },
    "custom": {"command": "", "report": "", "select": "env", "catalog": "", "env": {}},
}

_DOTENV_LINE = re.compile(r"^\s*(?:export\s+)?(TESTHARBOR_[A-Z_]+)\s*=\s*(.*?)\s*$")


def find_config(start: Path) -> Path | None:
    """testharbor.toml / .json in `start` or the nearest parent directory that has one."""
    for folder in (start, *start.parents):
        for name in CONFIG_NAMES:
            if (folder / name).is_file():
                return folder / name
    return None


def load_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        try:
            data = json.loads(text)
        except ValueError as e:
            raise CliError(f"{path}: not valid JSON ({e})") from e
    else:
        try:
            import tomllib
        except ImportError as e:  # Python < 3.11
            raise CliError(f"{path}: reading TOML needs Python 3.11+; use testharbor.json instead") from e
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            raise CliError(f"{path}: {e}") from e
    if not isinstance(data, dict):
        raise CliError(f"{path}: expected a table of settings")
    data = data.get("testharbor", data) if isinstance(data.get("testharbor"), dict) else data
    unknown = sorted(set(data) - KEYS)
    if unknown:
        raise CliError(f"{path}: unknown setting {unknown[0]!r} (known: {', '.join(sorted(KEYS))})")
    framework = data.get("framework", "custom")
    if framework not in FRAMEWORKS:
        raise CliError(f"{path}: framework must be one of {', '.join(FRAMEWORKS)}")
    if "select" in data and data["select"] not in SELECT_MODES:
        raise CliError(f"{path}: select must be one of {', '.join(SELECT_MODES)}")
    if "env" in data and not (isinstance(data["env"], dict) and all(isinstance(v, str) for v in data["env"].values())):
        raise CliError(f"{path}: env must be a table of strings")
    preset = PRESETS[framework]
    merged = {**preset, **data, "env": {**preset["env"], **data.get("env", {})}, "framework": framework}
    for key in ("setup", "secrets"):
        commands = merged.get(key, [])
        if isinstance(commands, str):
            commands = [commands]
        if not (isinstance(commands, list) and all(isinstance(c, str) for c in commands)):
            raise CliError(f"{path}: {key} must be a command or a list of commands")
        merged[key] = commands
    if not merged.get("command"):
        raise CliError(f"{path}: set `command` (how to run the tests)")
    if not merged.get("report"):
        raise CliError(f"{path}: set `report` (the JUnit XML or Playwright JSON file(s) the command writes)")
    return merged


def read_dotenv(folder: Path) -> dict[str, str]:
    """TESTHARBOR_* lines of folder/.env, as plain KEY=VALUE (nothing is executed or expanded)."""
    path = folder / ".env"
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _DOTENV_LINE.match(line)
        if not m:
            continue
        value = m.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value:
            out[m.group(1)] = value
    return out


def run_prepare(command: str, cwd: Path, log=print) -> None:  # type: ignore[no-untyped-def]
    args = shlex.split(command, posix=os.name != "nt")
    if args and (exe := shutil.which(args[0])):
        args[0] = exe
    log(f"  prepare: {command}")
    env = {k: v for k, v in os.environ.items() if k != "TESTHARBOR_TOKEN"}
    try:
        done = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.SubprocessError) as e:
        raise CliError(f"prepare failed: {e}") from e
    if done.returncode != 0:
        tail = "\n".join((done.stdout + done.stderr).strip().splitlines()[-15:])
        raise CliError(f"prepare exited with code {done.returncode}:\n{tail}")


# --- testcli init --------------------------------------------------------------------------


def detect_framework(folder: Path) -> str:
    if any(folder.glob("playwright.config.*")):
        return "playwright"
    pyproject = folder / "pyproject.toml"
    if (folder / "pytest.ini").is_file() or (folder / "conftest.py").is_file() or (
        pyproject.is_file() and "[tool.pytest" in pyproject.read_text(encoding="utf-8", errors="replace")
    ):
        return "pytest"
    return "custom"


def _python_runner(folder: Path) -> str:
    if (folder / "uv.lock").is_file():
        return "uv run pytest"
    if (folder / "poetry.lock").is_file():
        return "poetry run pytest"
    return "python -m pytest"


def init_text(folder: Path, url: str, project: int | None, framework: str | None = None) -> str:
    fw = framework or detect_framework(folder)
    lines = [
        "# TestHarbor: how `testcli agent` runs these tests. Docs: <TestHarbor>/docs, or docs/integration.md.",
        "# The API token is never written here: put TESTHARBOR_TOKEN=... into .env (git-ignored) or the environment.",
        f'url = "{url}"' if url else '# url = "https://testharbor.example.com"   # or TESTHARBOR_URL',
        f"project = {project}" if project else "# project = 1   # or TESTHARBOR_PROJECT",
        f'framework = "{fw}"',
    ]
    if fw == "pytest":
        runner = _python_runner(folder)
        lines += [f'command = "{runner} --junitxml=reports/junit.xml"', '# report = "reports/junit.xml"',
                  "# select = \"args\"   # selected tests are passed as node ids"]
    elif fw == "playwright":
        lines += ['# command = "npx playwright test --reporter=list,json,html"', '# report = "reports/results.json"',
                  '# select = "grep"   # selected tests are passed as --grep of their titles']
    else:
        lines += ['command = "./run-tests.sh"   # how to run your tests',
                  'report = "reports/*.xml"      # JUnit XML (or Playwright JSON) it writes; a glob, may use {job_id}',
                  '# select = "env"   # the command reads the selection from the JSON file in TESTHARBOR_SELECTION',
                  '# catalog = "testharbor-catalog.json"   # the list of tests, for TestHarbor\'s Autotests page',
                  '# options = "testharbor-options.json"   # run options people pick in TestHarbor',
                  '# prepare = "./make-catalog.sh"         # runs first, e.g. to write the two files above']
    lines += ['# report_url = "http://localhost:9323/index.html"   # where the HTML report opens', ""]
    return "\n".join(lines)


def env_is_ignored(folder: Path) -> bool | None:
    """Whether git ignores folder/.env (None: not a git checkout)."""
    try:
        done = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=folder, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return {0: True, 1: False}.get(done.returncode)


def agent_kwargs(conf: dict[str, Any], cwd: Path, read_options: bool = True) -> dict[str, Any]:
    """AgentConfig fields from a loaded testharbor.toml (connection and flags are added by the caller).
    read_options=False: the options file is read later (after `prepare` wrote it)."""
    from .agent import load_options

    options_file = conf.get("options")
    options = []
    if options_file and read_options and not conf.get("prepare"):
        options = load_options(cwd / str(options_file))
    return {
        "command": str(conf.get("command") or "npx playwright test"),
        "report": Path(str(conf.get("report") or "reports/results.json")),
        "cwd": cwd,
        "options": options,
        "options_file": Path(str(options_file)) if options_file else None,
        "catalog": str(conf["catalog"]) if conf.get("catalog") else None,
        "framework": str(conf.get("framework", "custom")),
        "select": str(conf.get("select", "")),
        "prepare": str(conf.get("prepare", "")),
        "extra_env": dict(conf.get("env", {})),
        "report_url": str(conf.get("report_url", "")),
        "auto_create": bool(conf.get("auto_create")),
        "grep_arg": str(conf.get("grep_arg", "--grep")),
    }


def run_secrets(commands: list[str], cwd: Path) -> None:
    """The `secrets` commands of a local agent, in the user's terminal (they may ask for an MFA code)."""
    import sys

    for command in commands:
        args = shlex.split(command, posix=os.name != "nt")
        if args and (exe := shutil.which(args[0])):
            args[0] = exe
        print(f"testcli: secrets: {command}", flush=True)
        if not sys.stdin.isatty():
            print("testcli: (no terminal to type into: if it asks for input, run it yourself first and start the "
                  "agent with --no-secrets)", flush=True)
        env = {k: v for k, v in os.environ.items() if k not in ("TESTHARBOR_TOKEN", "TESTHARBOR_GIT_TOKEN")}
        try:
            code = subprocess.run(args, cwd=cwd, env=env).returncode
        except OSError as e:
            raise CliError(f"secrets `{command}` could not start: {e}") from e
        if code != 0:
            raise CliError(f"secrets `{command}` exited with code {code} (skip it with --no-secrets if the "
                           "secrets are still valid)")
