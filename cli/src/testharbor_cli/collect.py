"""Built-in catalogs (the list of tests for TestHarbor) and selection of tests by key.

A test's key must be what its report carries, so TestHarbor matches results to cases by it:

* Playwright: `<file>::<describe › … › title>`, as TestHarbor names a test of a Playwright report
  (`npx playwright test --list --reporter=json` lists them). Selected tests run with `--grep`.
* pytest: the node id without the parameters (`tests/test_auth.py::TestLogin::test_ok`), as the
  JUnit report rebuilds it. Selected tests run as node id arguments.

Each test also gets the case text its code states (docstrings, comments, test.step titles,
annotations, pytest-bdd scenarios): see `describe.py`.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from . import describe
from .main import CliError

# A tag or marker that links a test to a case: C142, @C142, case:C142, case_C142.
_CASE_TAG = re.compile(r"^@?(?:case[:_-]?)?[Cc](\d+)$", re.IGNORECASE)
_CASE_ARG = re.compile(r"^\s*[Cc]?(\d+)\s*$")  # @pytest.mark.case("C142") or (142)


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


def playwright_catalog_from_list(report: dict[str, Any], root: Path | None = None) -> list[dict[str, Any]]:
    """Tests of `playwright test --list --reporter=json` output (one per spec, all projects merged).
    With `root` (where the spec files are), each test also gets what its source says about it."""
    tests: dict[str, dict[str, Any]] = {}
    sources: dict[str, str | None] = {}

    def source(file: str) -> str | None:
        if root is None or not file:
            return None
        if file not in sources:
            try:
                sources[file] = (root / file).read_text(encoding="utf-8", errors="replace")
            except OSError:
                sources[file] = None
        return sources[file]

    def walk(suite: dict[str, Any], titles: list[str], file: str) -> None:
        for spec in suite.get("specs") or []:
            name = " › ".join([*titles, spec.get("title", "")])
            path = spec.get("file") or file
            key = f"{path}::{name}"
            if key in tests:
                continue
            tags = [str(t).lstrip("@") for t in spec.get("tags") or []]
            entry = {
                "key": key,
                "title": spec.get("title") or "(unnamed)",
                "path": [p for p in [path, *titles] if p][:10],
                "tags": [t for t in tags if not _CASE_TAG.match(t)][:50],
                "case_ids": [int(m.group(1)) for t in spec.get("tags") or [] if (m := _CASE_TAG.match(str(t)))],
            }
            annotations = [a for t in spec.get("tests") or [] for a in t.get("annotations") or []]
            found = describe.playwright_found(source(path), spec, annotations)
            tests[key] = describe.finish(entry, found, path, spec.get("line"))
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
    root_dir = (report.get("config") or {}).get("rootDir")
    root = Path(root_dir) if root_dir and Path(root_dir).is_dir() else cwd
    return playwright_catalog_from_list(report, root)


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


# Markers that say how a test runs, not what it is about: not tags of its case.
_RUN_MARKERS = frozenset("""
    parametrize usefixtures skip skipif xfail filterwarnings case timeout flaky asyncio anyio trio
    django_db order run dependency no_cover tryfirst trylast forked repeat randomly serial
    xdist_group only_browser skip_browser browser_context_args scenario
""".split())


def _humanize_folder(name: str) -> str:
    text = name.replace("_", " ").replace("-", " ").strip()
    return text[:1].upper() + text[1:]


def _bdd_entry(base: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    first = rows[0]
    bdd = first["bdd"]
    feature_file = str(bdd.get("feature_file") or "")
    folders = list(Path(feature_file).parent.parts) if feature_file else []
    if folders and folders[0].lower() in ("features", "feature", "tests", "specs"):
        folders = folders[1:]
    preconditions, steps = describe.gherkin_case([(k, t) for k, t in bdd.get("steps") or []])
    parts = [bdd.get("feature_description") or "", bdd.get("scenario_description") or ""]
    examples = [r["bdd"]["example"] for r in rows if r.get("bdd", {}).get("example")]
    if examples:
        parts += ["Examples:", describe.examples_table(examples)]
    found = {"description": "\n\n".join(p for p in parts if p.strip()), "preconditions": preconditions,
             "steps": steps}
    entry = {
        "key": base,
        "title": bdd.get("scenario") or _humanize(base.rsplit("::", 1)[-1]),
        "path": [*(_humanize_folder(f) for f in folders), bdd.get("feature") or Path(feature_file).stem][:10],
    }
    return describe.finish(entry, found, feature_file, bdd.get("line"))


def pytest_catalog_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tests from the rows of the catalog plugin (`catalog_plugin.py`): parametrized tests merged."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        base = _PARAMS.sub("", str(row.get("nodeid") or ""))
        if "::" in base:
            groups.setdefault(base, []).append(row)
    out = []
    for base, group in groups.items():
        (entry,) = pytest_catalog_from_ids([base])
        first = group[0]
        markers = [m for r in group for m in r.get("markers") or []]
        names = list(dict.fromkeys(str(m.get("name")) for m in markers))
        case_ids = list(entry["case_ids"])
        for m in markers:
            if m.get("name") == "case":
                case_ids += [int(c.group(1)) for a in m.get("args") or [] if (c := _CASE_ARG.match(str(a)))]
        case_ids += [int(c.group(1)) for n in names if (c := _CASE_TAG.match(n))]
        tags = [n for n in names if n not in _RUN_MARKERS and not _CASE_TAG.match(n)
                and not n.startswith("_") and len(n) <= 100]
        if first.get("bdd"):
            entry = {**entry, **_bdd_entry(base, group)}
            tags += [t for t in first["bdd"].get("tags") or [] if not _CASE_TAG.match(t) and t not in tags]
            case_ids += [int(c.group(1)) for t in first["bdd"].get("tags") or [] if (c := _CASE_TAG.match(t))]
        else:
            title, rest = describe.title_and_doc(str(first.get("doc") or ""))
            if title:
                entry["title"] = title
            entry = describe.finish(entry, describe.parse_doc(rest), str(first.get("file") or base.split("::")[0]),
                                    first.get("line"))
        entry["tags"] = list(dict.fromkeys(tags))[:50]
        entry["case_ids"] = list(dict.fromkeys(case_ids))[:50]
        out.append(entry)
    return out


def pytest_catalog(command: str, cwd: Path) -> list[dict[str, Any]]:
    base = shlex.split(command, posix=os.name != "nt")
    args = [a for a in base if not a.startswith(("--junitxml", "--junit-xml"))]
    with tempfile.TemporaryDirectory(prefix="testharbor-catalog-") as tmp:
        # The plugin is copied out so it loads in the tests' own environment (testcli needn't be there).
        plugin = Path(tmp) / "testharbor_catalog.py"
        plugin.write_text((Path(__file__).parent / "catalog_plugin.py").read_text(encoding="utf-8"), encoding="utf-8")
        rows_file = Path(tmp) / "rows.json"
        pythonpath = os.pathsep.join(x for x in (tmp, os.environ.get("PYTHONPATH", "")) if x)
        collect = [*args, "--collect-only", "-q", "-p", "no:randomly"]
        try:
            out = _run([*collect, "-p", "testharbor_catalog"], cwd,
                       {"PYTHONPATH": pythonpath, "TESTHARBOR_CATALOG_OUT": str(rows_file)})
        except CliError:  # the command doesn't pass PYTHONPATH on (e.g. pytest in a container): ids only
            out = _run(collect, cwd)
        try:
            rows = json.loads(rows_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rows = None
    if isinstance(rows, list) and rows:
        return pytest_catalog_from_rows(rows)
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
