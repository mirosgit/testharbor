"""Turn CSV exports from TestHarbor and other tools into case rows.

Understands TestHarbor's own export plus the common shapes of BrowserStack Test Management and
TestRail exports. Columns are matched by name (case/spacing-insensitive, with aliases); values
like "Cannot Be Automated" or "1 - Critical" are mapped to TestHarbor's enums. Anything that
can't be mapped is reported instead of silently dropped.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any

from app.models import AutomationStatus, CaseType, Priority

_STEP_LINE = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
_LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_NUMBER_GAP = re.compile(r"^(\s*\d+[.)])\s{2,}")


def norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (h or "").lower()).strip("_")


# Field -> accepted (normalized) column names, in order of preference.
ALIASES: dict[str, tuple[str, ...]] = {
    "title": ("title", "name", "test_case_title", "case_title", "test_case_name", "summary"),
    "section_path": ("section_path", "folder_path", "section_hierarchy", "section", "folder", "path"),
    "description": ("description",),
    "preconditions": ("preconditions", "precondition", "pre_conditions", "prerequisites"),
    "steps": ("steps", "test_steps", "steps_step", "step"),
    "expected_result": ("expected_result", "expected_results", "steps_expected_result", "expected",
                        "expected_outcome"),
    "priority": ("priority",),
    "type": ("type", "type_of_test_case", "test_type", "case_type", "test_case_type"),
    "tags": ("tags", "labels", "tag", "label"),
    "automation_status": ("automation_status", "automation", "automation_state"),
    "automation_key": ("automation_key",),
    "external_id": ("external_id", "test_case_id", "case_id", "key", "test_id", "issue_key"),
}


@dataclass
class ParsedCsv:
    rows: list[dict[str, Any]]
    own_format: bool  # exported by TestHarbor: `id` is a TestHarbor case id
    ignored_columns: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --- Text helpers ----------------------------------------------------------------------


def unwrap(text: str) -> str:
    """Join hard-wrapped continuation lines (indented, not list items) onto the previous line,
    and tidy "1.  item" to "1. item". Keeps real line breaks and nested lists."""
    out: list[str] = []
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        if out and out[-1].strip() and line[:1] in (" ", "\t") and line.strip() and not _LIST_MARKER.match(line):
            out[-1] = f"{out[-1]} {line.strip()}"
        else:
            out.append(_NUMBER_GAP.sub(r"\1 ", line))
    return "\n".join(out).strip("\n")


def steps_to_text(steps: list[dict[str, Any]]) -> str:
    lines = []
    for i, s in enumerate(steps, 1):
        action, expected = s.get("action", ""), s.get("expected", "")
        lines.append(f"{i}. {action} => {expected}" if expected else f"{i}. {action}")
    return "\n".join(lines)


def text_to_steps(text: str) -> list[dict[str, str]]:
    """Numbered lines ("1. action => expected") start steps; other lines continue the previous
    step. If nothing is numbered, every non-empty line is a step."""
    lines = unwrap(text).split("\n") if text else []
    if not any(_STEP_LINE.match(ln) for ln in lines):
        chunks = [ln.strip() for ln in lines if ln.strip()]
    else:
        chunks = []
        for ln in lines:
            m = _STEP_LINE.match(ln)
            if m:
                chunks.append(m.group(2))
            elif chunks and ln.strip():
                chunks[-1] += "\n" + ln
    out = []
    for chunk in chunks:
        action, sep, expected = chunk.partition("=>")
        out.append({"action": action.strip(), "expected": expected.strip() if sep else ""})
    return out


# --- Value mapping -------------------------------------------------------------------

_EMPTY = {"", "undefined", "not set", "none", "-", "n/a", "null"}

_PRIORITY = {
    Priority.critical: {"critical", "blocker", "highest", "urgent", "p0", "must"},
    Priority.high: {"high", "major", "p1"},
    Priority.medium: {"medium", "normal", "moderate", "p2", "default"},
    Priority.low: {"low", "minor", "trivial", "lowest", "p3", "p4"},
}

_TYPE = {
    CaseType.functional: {"functional", "functionality"},
    CaseType.regression: {"regression"},
    CaseType.smoke: {"smoke", "sanity", "smoke & sanity", "smoke and sanity"},
    CaseType.acceptance: {"acceptance", "uat", "user acceptance"},
    CaseType.performance: {"performance", "load", "stress"},
    CaseType.security: {"security", "penetration"},
    CaseType.other: {"other", "usability", "accessibility", "compatibility", "integration", "e2e",
                     "end to end", "end-to-end", "exploratory", "automated", "destructive"},
}


def map_priority(value: str) -> tuple[Priority | None, str | None]:
    t = re.sub(r"^\d+\s*-\s*", "", (value or "").strip().lower())  # "1 - Critical" -> "critical"
    if t in _EMPTY:
        return None, None
    for p, names in _PRIORITY.items():
        if t in names:
            return p, None
    return None, f"priority {value!r} not recognized, used medium"


def map_type(value: str) -> tuple[CaseType | None, str | None]:
    t = (value or "").strip().lower()
    if t in _EMPTY:
        return None, None
    for ct, names in _TYPE.items():
        if t in names:
            return ct, None
    return CaseType.other, f"type {value!r} not recognized, used other"


def map_automation(value: str) -> tuple[AutomationStatus | None, str | None]:
    t = re.sub(r"[_\s]+", " ", (value or "").strip().lower())
    if t in _EMPTY:
        return None, None
    if any(x in t for x in ("cannot", "can not", "can't", "not applicable", "manual", "won't", "not automat")) \
            or t in ("no", "false"):
        return AutomationStatus.manual, None
    if any(x in t for x in ("to be automated", "in progress", "planned", "candidate", "todo", "to do",
                            "backlog", "automatable", "pending")):
        return AutomationStatus.to_be_automated, None
    if "automated" in t or t in ("yes", "true", "done"):
        return AutomationStatus.automated, None
    return None, f"automation status {value!r} not recognized, used manual"


# --- CSV -------------------------------------------------------------------------------


def _delimiter(text: str) -> str:
    header = text.split("\n", 1)[0]
    return max((",", ";", "\t"), key=header.count)


def parse_csv(text: str) -> ParsedCsv:
    """Rows as dicts with TestHarbor field names (values still strings/lists, unvalidated)."""
    reader = csv.reader(io.StringIO(text), delimiter=_delimiter(text))
    try:
        headers = next(reader)
    except StopIteration:
        raise ValueError("The file is empty") from None
    normalized = [norm_header(h) for h in headers]
    own_format = "section_path" in normalized
    aliases = dict(ALIASES)
    aliases["id" if own_format else "external_id"] = (
        ("id",) if own_format else ("id",) + ALIASES["external_id"]
    )

    column: dict[str, int] = {}  # field -> column index
    for fld, names in aliases.items():
        for name in names:
            if name in normalized and normalized.index(name) not in column.values():
                column[fld] = normalized.index(name)
                break
    if "title" not in column:
        raise ValueError(f"No title column found (columns: {', '.join(h for h in headers if h)})")

    # Keep the record number (header = 1) for messages; skip blank rows.
    raw_rows = [(n, r) for n, r in enumerate(reader, start=2) if any(c.strip() for c in r)]
    used = set(column.values())
    ignored = [
        headers[i] for i in range(len(headers))
        if i not in used and headers[i].strip() and any(i < len(r) and r[i].strip() for _, r in raw_rows)
    ]

    def cell(r: list[str], fld: str) -> str:
        i = column.get(fld)
        return r[i] if i is not None and i < len(r) else ""

    rows, warnings = [], []
    for n, r in raw_rows:
        pre = unwrap(cell(r, "preconditions"))
        desc = unwrap(cell(r, "description"))
        if desc:
            pre = f"{desc}\n\n{pre}" if pre else desc
        row: dict[str, Any] = {
            "_line": n,
            "id": cell(r, "id"),
            "external_id": cell(r, "external_id").strip() or None,
            "section_path": cell(r, "section_path"),
            "title": " ".join(cell(r, "title").split()),
            "preconditions": pre,
            "steps": text_to_steps(cell(r, "steps")),
            "expected_result": unwrap(cell(r, "expected_result")),
            "tags": [t for t in re.split(r"[,;]", cell(r, "tags"))],
            "automation_key": cell(r, "automation_key"),
        }
        for fld, mapper in (("priority", map_priority), ("type", map_type),
                            ("automation_status", map_automation)):
            if fld in column:
                value, warning = mapper(cell(r, fld))
                row[fld] = value.value if value else None
                if warning:
                    warnings.append(f"row {n}: {warning}")
        rows.append(row)
    return ParsedCsv(rows=rows, own_format=own_format, ignored_columns=ignored, warnings=warnings)
