"""JUnit XML parsing and mapping of test cases to TestHarbor cases.

Supports the common dialects: pytest (xunit1/xunit2), Playwright, Jest (jest-junit),
Maven Surefire / Gradle (JUnit 4/5, TestNG), Cypress (mocha-junit-reporter).

Mapping order for each <testcase>:
  1. Case id: a `case_id` property (comma-separated allowed), else `C123` in the test name.
  2. automation_key: an `automation_key` property, or keys derived from classname/name/file.
  3. Otherwise unmatched (or auto-created when requested).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element

from defusedxml import ElementTree as SafeET

from app.models import ResultStatus

# "C142" at the start or after a non-alphanumeric char (so `test_login_C142`, `[C142] login`,
# `C142: login` match, but `ABC142` or `TC142` don't), and not followed by another digit.
CASE_ID_IN_NAME = re.compile(r"(?<![A-Za-z0-9])C(\d+)(?!\d)")
CASE_ID_VALUE = re.compile(r"^\s*[Cc]?(\d+)\s*$")
CASE_ID_PROPERTIES = {"case_id", "case_ids", "caseid", "testharbor_case_id", "test_case_id"}
KEY_PROPERTIES = {"automation_key", "testharbor_key", "nodeid"}
# A link to this test's details in an HTML report: an absolute URL, or a Playwright test id
# that is appended to the run's report URL as "#?testId=<id>".
LINK_PROPERTIES = {"report_url", "report_link", "testharbor_link", "link", "url"}
TEST_ID_PROPERTIES = {"pw_test_id", "playwright_test_id", "testid"}
# The configuration a test ran in (a role, a browser, a Playwright project), shown with its result.
CONFIG_PROPERTIES = {"config", "configuration", "testharbor_config"}

MAX_TEXT = 64 * 1024  # cap stored message/trace size per result


@dataclass
class JUnitCase:
    name: str
    classname: str = ""
    file: str = ""
    time_s: float | None = None
    status: ResultStatus = ResultStatus.passed
    message: str | None = None
    details: str | None = None
    properties: dict[str, list[str]] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return f"{self.classname}::{self.name}" if self.classname else self.name

    def case_ids(self) -> list[int]:
        """Explicit case ids, from properties first, else from the test name."""
        ids: list[int] = []
        for prop, values in self.properties.items():
            if prop.lower() in CASE_ID_PROPERTIES:
                for v in values:
                    for part in re.split(r"[,\s]+", v):
                        m = CASE_ID_VALUE.match(part)
                        if m:
                            ids.append(int(m.group(1)))
        if not ids:
            ids = [int(m) for m in CASE_ID_IN_NAME.findall(self.name)]
        return list(dict.fromkeys(ids))

    def explicit_key(self) -> str | None:
        for prop, values in self.properties.items():
            if prop.lower() in KEY_PROPERTIES and values and values[0].strip():
                return values[0].strip()
        return None

    def candidate_keys(self) -> list[str]:
        """automation_key candidates, most specific first."""
        keys: list[str] = []
        if k := self.explicit_key():
            keys.append(k)
        cn, name = self.classname, self.name
        if cn:
            keys += [f"{cn}::{name}", f"{cn}.{name}"]
            # pytest: classname "tests.api.test_auth.TestLogin" -> "tests/api/test_auth.py::TestLogin::name".
            # We don't know where the module ends and classes begin, so try every split.
            parts = cn.split(".")
            if "/" not in cn and all(parts):
                for i in range(len(parts), 0, -1):
                    module = "/".join(parts[:i]) + ".py"
                    keys.append("::".join([module, *parts[i:], name]))
        if self.file:
            keys.append(f"{self.file}::{name}")
            if cn:
                cls = cn.rsplit(".", 1)[-1]
                keys.append(f"{self.file}::{cls}::{name}")
        keys.append(name)
        return list(dict.fromkeys(keys))

    def default_key(self) -> str:
        """automation_key to store on an auto-created case."""
        return self.explicit_key() or self.display_name

    def report_link(self) -> str | None:
        """Absolute http(s) URL, or "#?testId=…" relative to the run's report URL."""
        for prop, values in self.properties.items():
            if prop.lower() in LINK_PROPERTIES:
                for v in values:
                    if re.match(r"^https?://\S+$", v.strip(), re.I) and len(v.strip()) <= 2000:
                        return v.strip()
        for prop, values in self.properties.items():
            if prop.lower() in TEST_ID_PROPERTIES:
                for v in values:
                    if re.fullmatch(r"[A-Za-z0-9_-]{1,200}", v.strip()):
                        return f"#?testId={v.strip()}"
        return None

    def config(self) -> str | None:
        for prop, values in self.properties.items():
            if prop.lower() in CONFIG_PROPERTIES:
                for v in values:
                    if v.strip():
                        return v.strip()[:200]
        return None

    def duration_ms(self) -> int | None:
        return None if self.time_s is None else max(0, round(self.time_s * 1000))


class JUnitParseError(ValueError):
    pass


def _clip(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    return s if len(s) <= MAX_TEXT else s[:MAX_TEXT] + "\n… (truncated)"


def _float(v: str | None) -> float | None:
    try:
        return float(v.replace(",", "")) if v else None
    except ValueError:
        return None


def _properties(el: Element) -> dict[str, list[str]]:
    props: dict[str, list[str]] = {}
    for p in el.findall("./properties/property"):
        name = p.get("name")
        if not name:
            continue
        value = p.get("value")
        if value is None:
            value = p.text or ""
        props.setdefault(name, []).append(value)
    return props


def _parse_testcase(el: Element) -> JUnitCase:
    tc = JUnitCase(
        name=(el.get("name") or "").strip() or "(unnamed)",
        classname=(el.get("classname") or el.get("class") or "").strip(),
        file=(el.get("file") or "").strip(),
        time_s=_float(el.get("time")),
        properties=_properties(el),
    )
    failure = el.find("failure")
    error = el.find("error")
    skipped = el.find("skipped")
    problem = failure if failure is not None else error
    out = "\n".join(t for t in ((el.findtext("system-out") or "").strip(),
                                (el.findtext("system-err") or "").strip()) if t)
    if problem is not None:
        tc.status = ResultStatus.failed
        text = (problem.text or "").strip()
        msg = (problem.get("message") or "").strip() or (text.splitlines()[0] if text else "")
        if problem.tag == "error":
            msg = f"[error] {msg}" if msg else "[error]"
        if problem.get("type") and problem.get("type") not in msg:
            msg = f"{problem.get('type')}: {msg}" if msg else problem.get("type", "")
        tc.message = _clip(msg)
        tc.details = _clip("\n\n".join(t for t in (text, out) if t))
    elif skipped is not None:
        tc.status = ResultStatus.skipped
        tc.message = _clip(skipped.get("message") or skipped.text)
        tc.details = _clip(out)
    else:
        tc.details = _clip(out)
    return tc


def parse_junit(data: bytes) -> list[JUnitCase]:
    """Parse a JUnit XML document into a flat list of test cases."""
    try:
        root = SafeET.fromstring(data)
    except SafeET.ParseError as e:
        raise JUnitParseError(f"Invalid XML: {e}") from e
    except Exception as e:  # defusedxml raises its own errors for entity attacks etc.
        raise JUnitParseError(f"Rejected XML: {e.__class__.__name__}") from e
    if root.tag not in ("testsuites", "testsuite", "testcase"):
        raise JUnitParseError(f"Not a JUnit report (root element <{root.tag}>)")
    elements = [root] if root.tag == "testcase" else list(root.iter("testcase"))
    return [_parse_testcase(el) for el in elements]


# Order for writing several results for the same case in one import: the worst status
# is written last so it becomes the current one (e.g. parametrized tests sharing a case id).
STATUS_SEVERITY = {
    ResultStatus.passed: 0,
    ResultStatus.skipped: 1,
    ResultStatus.untested: 1,
    ResultStatus.retest: 2,
    ResultStatus.blocked: 3,
    ResultStatus.failed: 4,
}
