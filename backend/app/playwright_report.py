"""Playwright's JSON reporter output (`reporter: [["json", { outputFile }]]`).

Turned into the same JUnitCase records as a JUnit report, named the way Playwright's JUnit
reporter names tests ("Describe › title", classname = spec file), so matching rules and
automation keys are the same for both formats. On top of JUnit it carries each test's id,
which deep-links into Playwright's HTML report (`index.html#?testId=<id>`).

Case ids come from a `case_id` annotation, a `@C123` tag, or `C123` in the title.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.junit import JUnitCase, JUnitParseError, _clip
from app.models import ResultStatus

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_TAG_CASE_ID = re.compile(r"^@?[Cc](\d+)$")


def _plain(text: str | None) -> str:
    return _ANSI.sub("", text or "").strip()


def _output(chunks: list[Any]) -> str:
    parts = []
    for c in chunks or []:
        if isinstance(c, dict):
            parts.append(c.get("text") or "")
        elif isinstance(c, str):
            parts.append(c)
    return _plain("".join(parts))


def _test_case(spec: dict[str, Any], test: dict[str, Any], titles: list[str], multi_project: bool) -> JUnitCase:
    results = test.get("results") or []
    last = results[-1] if results else {}
    name = " › ".join([*titles, spec.get("title", "")]).strip() or "(unnamed)"
    project = test.get("projectName") or ""
    if multi_project and project:
        name = f"[{project}] {name}"

    props: dict[str, list[str]] = {"pw_test_id": [str(spec.get("id", ""))]}
    if multi_project and project:
        props["config"] = [project]
    for a in test.get("annotations") or []:
        if isinstance(a, dict) and a.get("type") and a.get("description") is not None:
            props.setdefault(str(a["type"]), []).append(str(a["description"]))
    for tag in spec.get("tags") or []:
        if m := _TAG_CASE_ID.match(str(tag)):
            props.setdefault("case_id", []).append(m.group(1))

    tc = JUnitCase(name=name, classname=spec.get("file", ""), properties=props)
    duration = last.get("duration")
    tc.time_s = duration / 1000 if isinstance(duration, (int, float)) and duration >= 0 else None

    outcome = test.get("status")  # expected | unexpected | flaky | skipped
    errors = [e for r in results for e in (r.get("errors") or [])] if outcome == "unexpected" else []
    out = "\n".join(t for t in (_output(last.get("stdout")), _output(last.get("stderr"))) if t)
    if outcome == "skipped" or (outcome == "expected" and last.get("status") == "skipped"):
        tc.status = ResultStatus.skipped
        reason = next((a.get("description") for a in test.get("annotations") or []
                       if isinstance(a, dict) and a.get("type") in ("skip", "fixme") and a.get("description")), None)
        tc.message = _clip(reason)
    elif outcome == "unexpected":
        tc.status = ResultStatus.failed
        last_errors = last.get("errors") or errors
        first = last_errors[0] if last_errors else {}
        message = _plain(first.get("message")) or f"Test {last.get('status', 'failed')}"
        if last.get("status") == "timedOut" and "timeout" not in message.lower():
            message = f"Timed out. {message}"
        tc.message = _clip(message)
        stack = _plain((last.get("error") or {}).get("stack")) or "\n\n".join(_plain(e.get("message")) for e in last_errors)
        tc.details = _clip("\n\n".join(t for t in (stack, out) if t))
    else:
        tc.status = ResultStatus.passed
        if outcome == "flaky":
            tc.message = f"Flaky: passed on retry {last.get('retry', len(results) - 1)}"
        tc.details = _clip(out)
    return tc


def looks_like_playwright_json(data: bytes) -> bool:
    return data.lstrip()[:1] == b"{"


def parse_playwright_json(data: bytes) -> list[JUnitCase]:
    try:
        report = json.loads(data)
    except (ValueError, UnicodeDecodeError) as e:
        raise JUnitParseError(f"Invalid JSON: {e}") from e
    if not isinstance(report, dict) or not isinstance(report.get("suites"), list):
        raise JUnitParseError("Not a Playwright JSON report (no \"suites\")")
    projects = {p.get("name") for p in (report.get("config") or {}).get("projects") or [] if isinstance(p, dict)}
    multi = len(projects) > 1

    cases: list[JUnitCase] = []

    def walk(suite: dict[str, Any], titles: list[str]) -> None:
        for spec in suite.get("specs") or []:
            for test in spec.get("tests") or []:
                cases.append(_test_case(spec, test, titles, multi))
        for child in suite.get("suites") or []:
            walk(child, [*titles, child.get("title", "")])

    for file_suite in report["suites"]:
        walk(file_suite, [])  # the top-level suite is the file; its title is not part of the name
    return cases
