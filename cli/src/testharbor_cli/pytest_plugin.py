"""pytest plugin: link tests to TestHarbor cases.

    @pytest.mark.case("C142")
    def test_login(): ...

    @pytest.mark.case("C142", "C143")   # one test covering several cases
    @pytest.mark.case(144)              # ints work too

The ids are written to the JUnit XML report (`pytest --junitxml=report.xml`) as a
`case_id` property. Every test also gets an `automation_key` property with its node id
(e.g. `tests/test_auth.py::test_login`) so TestHarbor can match it exactly.

Disable the plugin with `-p no:testharbor`.
"""

from __future__ import annotations

import re

import pytest

_CASE = re.compile(r"^\s*[Cc]?(\d+)\s*$")


def _normalize(value: object) -> str:
    m = _CASE.match(str(value))
    if not m or isinstance(value, bool):
        raise pytest.UsageError(f"@pytest.mark.case: invalid case id {value!r} (expected e.g. 'C142' or 142)")
    return f"C{int(m.group(1))}"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "case(*ids): link this test to TestHarbor case ids, e.g. @pytest.mark.case('C142')"
    )


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        ids: list[str] = []
        for marker in item.iter_markers("case"):
            ids.extend(_normalize(a) for a in marker.args)
        if ids:
            item.user_properties.append(("case_id", ",".join(dict.fromkeys(ids))))
        item.user_properties.append(("automation_key", item.nodeid))
