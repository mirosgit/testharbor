"""pytest plugin used by `testcli agent` to list tests with what their code says about them.

The agent copies this file next to nothing else and loads it with `-p testharbor_catalog` during
`pytest --collect-only`, so it works in the tests' own environment without installing testcli
there. It only reads: for every collected test it writes its node id, location, docstring, markers
and, for a pytest-bdd scenario, the feature and the scenario (steps, tags, the Examples row) to the
JSON file named by TESTHARBOR_CATALOG_OUT. Stdlib + pytest only; any failure leaves a test with less
detail, never breaks the collection.
"""

from __future__ import annotations

import inspect
import json
import os
from typing import Any


def _text(value: object) -> str:
    return "\n".join(line.strip() for line in str(value or "").strip().splitlines()).strip()


def _scenario(obj: Any) -> Any:
    try:
        from pytest_bdd.scenario import scenario_wrapper_template_registry  # pytest-bdd >= 7

        found = scenario_wrapper_template_registry.get(obj)
        if found is not None:
            return found
    except Exception:
        pass
    return getattr(obj, "__scenario__", None)  # older pytest-bdd


def _bdd(item: Any) -> dict[str, Any] | None:
    template = _scenario(getattr(item, "obj", None))
    if template is None:
        return None
    feature = template.feature
    callspec = getattr(item, "callspec", None)
    example = callspec.params.get("_pytest_bdd_example") if callspec is not None else None
    filename = getattr(feature, "rel_filename", None) or getattr(feature, "filename", "") or ""
    try:
        filename = os.path.relpath(filename, str(item.config.rootpath)) if os.path.isabs(filename) else filename
    except Exception:
        pass
    return {
        "feature": str(getattr(feature, "name", "") or ""),
        "feature_file": str(filename).replace(os.sep, "/"),
        "feature_description": _text(getattr(feature, "description", "")),
        "scenario": str(getattr(template, "name", "") or ""),
        "scenario_description": _text(getattr(template, "description", "")),
        "line": getattr(template, "line_number", None),
        "tags": sorted({*map(str, getattr(feature, "tags", ()) or ()), *map(str, getattr(template, "tags", ()) or ())}),
        "steps": [[str(s.keyword), str(s.name)] for s in getattr(template, "steps", ()) or ()],
        "example": {str(k): str(v) for k, v in dict(example).items()} if example is not None else None,
    }


def _describe(item: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"nodeid": item.nodeid}
    try:
        file, line, _ = item.location
        row["file"], row["line"] = str(file).replace(os.sep, "/"), (line + 1 if line is not None else None)
    except Exception:
        pass
    try:
        obj = getattr(item, "obj", None)
        if obj is not None and getattr(obj, "__doc__", None):
            row["doc"] = inspect.cleandoc(obj.__doc__)
    except Exception:
        pass
    try:
        markers = []
        for mark in item.iter_markers():
            markers.append({"name": mark.name, "args": [a for a in mark.args if isinstance(a, (str, int))]})
        row["markers"] = markers
    except Exception:
        pass
    try:
        if (bdd := _bdd(item)) is not None:
            row["bdd"] = bdd
    except Exception:
        pass
    return row


def pytest_collection_finish(session: Any) -> None:
    out = os.environ.get("TESTHARBOR_CATALOG_OUT")
    if not out:
        return
    rows = [_describe(item) for item in session.items]
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, default=str)
