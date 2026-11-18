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
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.models import AutomationComplexity, AutomationProgress, AutomationStatus, CaseState, CaseType, Priority

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
    "state": ("state", "case_state", "test_case_state"),
    "owner": ("owner", "case_owner", "assignee", "assigned_to"),
    "automation_complexity": ("automation_complexity", "complexity"),
    "automation_progress": ("automation_progress", "automation_status_custom"),
    "sprint": ("sprint", "sprint_no", "sprint_number", "iteration"),
    "roles": ("roles", "applicable_roles", "role", "user_roles"),
    "created_at": ("created_at", "created_on", "created", "creation_date"),
    "updated_at": ("updated_at", "last_updated_at", "updated_on", "last_updated_on", "modified_at"),
    "updated_by": ("updated_by", "last_updated_by", "modified_by"),
}

# Built-in fields that older imports stored as custom fields (see migration 0005).
PROMOTED_FIELDS = ("state", "owner", "automation_complexity", "automation_progress", "sprint", "roles",
                   "created_at", "updated_at", "updated_by")


# Tool-internal columns that are not worth keeping as custom fields by default.
NOISE_COLUMNS = {"folder_id", "template_type", "template_name", "project_name", "test_case_url",
                 "ai_prompt", "project", "suite", "suite_id", "section_id", "section_description"}


@dataclass
class ParsedCsv:
    rows: list[dict[str, Any]]
    own_format: bool  # exported by TestHarbor: `id` is a TestHarbor case id
    # Columns with data but no built-in field: (header, imported as custom field?)
    extra_columns: list[tuple[str, bool]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ignored_columns(self) -> list[str]:
        return [name for name, selected in self.extra_columns if not selected]


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


def _norm_value(value: str) -> str:
    return re.sub(r"[_\s]+", " ", (value or "").strip().lower())


_STATE = {
    CaseState.draft: {"draft", "new"},
    CaseState.active: {"active", "approved", "ready", "actual"},
    CaseState.pending_review: {"pending review", "in review", "review", "under review", "needs review"},
    CaseState.outdated: {"outdated", "deprecated", "obsolete", "archived"},
    CaseState.rejected: {"rejected", "declined"},
}


def map_state(value: str) -> tuple[CaseState | None, str | None]:
    t = _norm_value(value)
    if t in _EMPTY:
        return None, None
    for st, names in _STATE.items():
        if t in names:
            return st, None
    return None, f"state {value!r} not recognized, used active"


def map_complexity(value: str) -> tuple[AutomationComplexity | None, str | None]:
    t = _norm_value(value)
    if t in _EMPTY:
        return None, None
    if t in ("n/a", "na") or re.search(r"not\s*a?p+li?cable", t):  # also the "Not Aplicable" typo
        return AutomationComplexity.not_applicable, None
    for c, names in ((AutomationComplexity.low, {"low", "easy", "simple"}),
                     (AutomationComplexity.medium, {"medium", "moderate", "normal"}),
                     (AutomationComplexity.high, {"high", "hard", "complex", "difficult"})):
        if t in names:
            return c, None
    return None, f"automation complexity {value!r} not recognized, left empty"


def map_progress(value: str) -> tuple[AutomationProgress | None, str | None]:
    t = _norm_value(value)
    if t in _EMPTY:
        return None, None
    if any(x in t for x in ("cannot", "can not", "can't", "not applicable", "won't")):
        return AutomationProgress.cannot_be_automated, None
    if any(x in t for x in ("progress", "in work", "ongoing", "started", "wip")):
        return AutomationProgress.in_progress, None
    if any(x in t for x in ("not automated", "to be automated", "to do", "todo", "backlog", "planned", "manual")):
        return AutomationProgress.not_automated, None
    if "automated" in t or t == "done":
        return AutomationProgress.automated, None
    return None, f"automation progress {value!r} not recognized, left empty"


_DATE_FORMATS = ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M %p", "%m/%d/%Y %I:%M:%S %p",
                 "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M",
                 "%d.%m.%Y")


def parse_datetime(value: str) -> tuple[datetime | None, str | None]:
    """ISO 8601, or US "06/22/2026 09:26:20" as BrowserStack/TestRail export it. No timezone = UTC."""
    t = (value or "").strip()
    if t.lower() in _EMPTY:
        return None, None
    dt = None
    try:
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        for fmt in _DATE_FORMATS:
            try:
                dt = datetime.strptime(t, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None, f"date {value!r} not recognized, ignored"
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)), None


def split_list(value: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,;\n]", value or "") if p.strip()]


# --- CSV -------------------------------------------------------------------------------


def _delimiter(text: str) -> str:
    header = text.split("\n", 1)[0]
    return max((",", ";", "\t"), key=header.count)


def parse_csv(text: str, columns: set[str] | None = None) -> ParsedCsv:
    """Rows as dicts with TestHarbor field names (values still strings/lists, unvalidated).

    Columns that have data but no built-in field become custom fields: the ones named in
    `columns` (matched case-insensitively), or by default all except other tools' internal ones.
    """
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
    extra_idx = [
        i for i in range(len(headers))
        if i not in used and headers[i].strip() and any(i < len(r) and r[i].strip() for _, r in raw_rows)
    ]
    wanted = {c.strip().lower() for c in columns} if columns is not None else None
    extra = [
        (i, headers[i].strip(),
         headers[i].strip().lower() in wanted if wanted is not None
         # In our own export every extra column is a custom field somebody created.
         else own_format or normalized[i] not in NOISE_COLUMNS)
        for i in extra_idx
    ]

    def cell(r: list[str], fld: str) -> str:
        i = column.get(fld)
        return r[i] if i is not None and i < len(r) else ""

    rows, warnings = [], []
    for n, r in raw_rows:
        pre = unwrap(cell(r, "preconditions"))
        row: dict[str, Any] = {
            "_line": n,
            "id": cell(r, "id"),
            "external_id": cell(r, "external_id").strip() or None,
            "section_path": cell(r, "section_path"),
            "title": " ".join(cell(r, "title").split()),
            "description": unwrap(cell(r, "description")),
            "preconditions": pre,
            "steps": text_to_steps(cell(r, "steps")),
            "expected_result": unwrap(cell(r, "expected_result")),
            "tags": [t for t in re.split(r"[,;]", cell(r, "tags"))],
            "automation_key": cell(r, "automation_key"),
            "owner": " ".join(cell(r, "owner").split()) or None,
            "sprint": " ".join(cell(r, "sprint").split()) or None,
            "updated_by": " ".join(cell(r, "updated_by").split()) or None,
            "custom_fields": [
                {"name": name, "value": unwrap(r[i]) if i < len(r) else ""}
                for i, name, selected in extra if selected and i < len(r) and r[i].strip()
            ],
        }
        if "roles" in column:
            row["roles"] = split_list(cell(r, "roles"))
        for fld, mapper in (("priority", map_priority), ("type", map_type),
                            ("automation_status", map_automation), ("state", map_state),
                            ("automation_complexity", map_complexity),
                            ("automation_progress", map_progress), ("created_at", parse_datetime),
                            ("updated_at", parse_datetime)):
            if fld in column:
                value, warning = mapper(cell(r, fld))
                row[fld] = value.value if isinstance(value, StrEnum) else value
                if warning:
                    warnings.append(f"row {n}: {warning}")
        rows.append(row)
    return ParsedCsv(rows=rows, own_format=own_format, warnings=warnings,
                     extra_columns=[(name, selected) for _, name, selected in extra])
