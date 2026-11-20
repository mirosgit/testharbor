"""Built-in catalogs (the list of tests for TestHarbor) and selection of tests by key.

A test's key must be what its report carries, so TestHarbor matches results to cases by it:

* Playwright: `<file>::<describe › … › title>`, as TestHarbor names a test of a Playwright report
  (`npx playwright test --list --reporter=json` lists them). Selected tests run with `--grep`.
* pytest: the node id without the parameters (`tests/test_auth.py::TestLogin::test_ok`), as the
  JUnit report rebuilds it. Selected tests run as node id arguments.
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

_CASE_TAG = re.compile(r"^@?C(\d+)$")


def _run(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    if args and (exe := shutil.which(args[0])):
        args = [exe, *args[1:]]
    environ = {k: v for k, v in os.environ.items() if k != "TESTHARBOR_TOKEN"}
    environ.update(env or {})
    try:
        done = subprocess.run(args, cwd=cwd, env=environ, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.SubprocessError) as e:
        raise CliError(f"{shlex.join(args)}: {e}") from e
    if done.returncode not in (0, 5):  # pytest: 5 = no tests collected
        tail = "\n".join((done.stdout + done.stderr).strip().splitlines()[-15:])
        raise CliError(f"{shlex.join(args)} exited with code {done.returncode}:\n{tail}")
    return done.stdout


# --- Playwright -----------------------------------------------------------------------------


def playwright_catalog_from_list(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Tests of `playwright test --list --reporter=json` output (one per spec, all projects merged)."""
    tests: dict[str, dict[str, Any]] = {}

    def walk(suite: dict[str, Any], titles: list[str], file: str) -> None:
        for spec in suite.get("specs") or []:
            name = " › ".join([*titles, spec.get("title", "")])
            path = spec.get("file") or file
            key = f"{path}::{name}"
            if key in tests:
                continue
            tags = [str(t).lstrip("@") for t in spec.get("tags") or []]
            tests[key] = {
                "key": key,
                "title": spec.get("title") or "(unnamed)",
                "path": [p for p in [path, *titles] if p][:10],
                "tags": [t for t in tags if not _CASE_TAG.match(t)][:50],
                "case_ids": [int(m.group(1)) for t in spec.get("tags") or [] if (m := _CASE_TAG.match(str(t)))],
            }
        for child in suite.get("suites") or []:
            walk(child, [*titles, child.get("title", "")], file)

    for file_suite in report.get("suites") or []:
        walk(file_suite, [], file_suite.get("file") or file_suite.get("title", ""))
    return list(tests.values())


def playwright_catalog(command: str, cwd: Path) -> list[dict[str, Any]]:
    base = shlex.split(command, posix=os.name != "nt")
    # `npx playwright test …` -> `npx playwright test --list --reporter=json` (other options dropped:
    # they are about running, and a --reporter would clash).
    try:
        i = base.index("test")
        args = base[: i + 1]
    except ValueError:
        args = ["npx", "playwright", "test"]
    out = _run([*args, "--list", "--reporter=json"], cwd, {"PLAYWRIGHT_JSON_OUTPUT_NAME": ""})
    try:
        report = json.loads(out[out.index("{"):])
    except ValueError as e:
        raise CliError(f"playwright --list did not print a JSON report: {out[:300]}") from e
    return playwright_catalog_from_list(report)


def grep_for_keys(keys: list[str], case_ids: list[int]) -> str:
    """One --grep regex: the titles of the selected tests, and @C<id> / C<id> of tagged cases."""
    parts = []
    for key in keys:
        title = key.split("::", 1)[-1]
        words = [re.escape(t) for t in title.split(" › ") if t]
        if words:
            parts.append(r"(?:^|\s)" + r"\s".join(words) + r"(?:\s|$)")
    if case_ids:
        parts.append(r"(?<![A-Za-z0-9])C(?:" + "|".join(str(int(i)) for i in case_ids) + r")(?![0-9])")
    return "|".join(parts)


# --- pytest ---------------------------------------------------------------------------------

_PARAMS = re.compile(r"\[.*\]$")


def _humanize(name: str) -> str:
    words = re.sub(r"^test_?", "", name).replace("_", " ").strip()
    return (words[:1].upper() + words[1:]) if words else name


def pytest_catalog_from_ids(nodeids: list[str]) -> list[dict[str, Any]]:
    tests: dict[str, dict[str, Any]] = {}
    for nodeid in nodeids:
        base = _PARAMS.sub("", nodeid)
        if base in tests or "::" not in base:
            continue
        file, *names = base.split("::")
        folders = [p for p in Path(file).with_suffix("").parts]
        tests[base] = {
            "key": base,
            "title": _humanize(names[-1]),
            "path": [*folders, *names[:-1]][:10],
            "tags": [],
            "case_ids": [int(m) for m in re.findall(r"(?<![A-Za-z0-9])C(\d+)(?!\d)", names[-1])],
        }
    return list(tests.values())


def pytest_catalog(command: str, cwd: Path) -> list[dict[str, Any]]:
    base = shlex.split(command, posix=os.name != "nt")
    args = [a for a in base if not a.startswith(("--junitxml", "--junit-xml"))]
    out = _run([*args, "--collect-only", "-q", "-p", "no:randomly"], cwd)
    ids = [line.strip() for line in out.splitlines() if "::" in line and not line.startswith(" ")]
    return pytest_catalog_from_ids(ids)


def pytest_args(keys: list[str]) -> list[str]:
    return list(dict.fromkeys(keys))


def build_catalog(framework: str, command: str, cwd: Path) -> list[dict[str, Any]]:
    if framework == "playwright":
        return playwright_catalog(command, cwd)
    if framework == "pytest":
        return pytest_catalog(command, cwd)
    raise CliError('catalog = "auto" works for framework = "playwright" or "pytest"; give a JSON file instead')
