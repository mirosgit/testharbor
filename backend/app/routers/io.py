"""Import / export of a suite's cases as CSV or JSON.

CSV columns: id, section_path, title, preconditions, steps, expected_result, priority, type,
tags, automation_status, automation_key.

- section_path: "Parent > Child". Missing sections are created on import.
- steps: one cell, numbered lines "1. action => expected". Lines without a number continue the
  previous step. If no line is numbered, every line is one step.
- tags: comma-separated.
- id: "C142" or "142". If that case exists in the suite it is updated; otherwise a new case is created.

JSON is lossless: {"format": "testharbor", "version": 1, "suite": {...}, "cases": [...]}.
A plain JSON list of case objects is accepted on import too.
"""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Section, Suite, TestCase
from app.schemas import CaseFields, ImportResult
from app.services import CASE_REF, get_or_404, section_paths, suite_sections, tree_order

router = APIRouter(prefix="/api", tags=["import/export"])
Session = Annotated[AsyncSession, Depends(get_session)]

CSV_COLUMNS = [
    "id", "section_path", "title", "preconditions", "steps", "expected_result",
    "priority", "type", "tags", "automation_status", "automation_key",
]
_STEP_LINE = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
_PATH_SEP = re.compile(r"\s*>\s*")
MAX_IMPORT_BYTES = 20 * 1024 * 1024


# --- Steps <-> text ------------------------------------------------------------------


def steps_to_text(steps: list[dict[str, Any]]) -> str:
    lines = []
    for i, s in enumerate(steps, 1):
        action, expected = s.get("action", ""), s.get("expected", "")
        lines.append(f"{i}. {action} => {expected}" if expected else f"{i}. {action}")
    return "\n".join(lines)


def text_to_steps(text: str) -> list[dict[str, str]]:
    lines = [ln for ln in (text or "").replace("\r\n", "\n").split("\n")]
    if not any(_STEP_LINE.match(ln) for ln in lines):
        chunks = [ln for ln in lines if ln.strip()]
    else:
        chunks = []
        for ln in lines:
            m = _STEP_LINE.match(ln)
            if m:
                chunks.append(m.group(2))
            elif chunks:
                chunks[-1] += "\n" + ln
    out = []
    for chunk in chunks:
        action, sep, expected = chunk.partition("=>")
        out.append({"action": action.strip(), "expected": expected.strip() if sep else ""})
    return out


# --- Export --------------------------------------------------------------------------


async def _export_rows(session: AsyncSession, suite: Suite) -> list[dict[str, Any]]:
    sections = await suite_sections(session, suite.id)
    paths = section_paths(sections)
    order = {sid: i for i, sid in enumerate(tree_order(sections))}
    cases = list(await session.scalars(select(TestCase).where(TestCase.suite_id == suite.id)))
    cases.sort(key=lambda c: (order.get(c.section_id, 0), c.position, c.id))
    return [
        {
            "id": c.key,
            "section_path": paths[c.section_id],
            "title": c.title,
            "preconditions": c.preconditions,
            "steps": c.steps,
            "expected_result": c.expected_result,
            "priority": c.priority.value,
            "type": c.type.value,
            "tags": c.tags,
            "automation_status": c.automation_status.value,
            "automation_key": c.automation_key,
        }
        for c in cases
    ]


def _filename(suite: Suite, ext: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", suite.name).strip("-").lower() or "suite"
    return f"{slug}-cases.{ext}"


@router.get("/suites/{suite_id}/export")
async def export_suite(
    suite_id: int, session: Session, format: Literal["csv", "json"] = "csv"
) -> Response:
    suite = await get_or_404(session, Suite, suite_id)
    rows = await _export_rows(session, suite)
    if format == "json":
        payload = {
            "format": "testharbor",
            "version": 1,
            "suite": {"name": suite.name, "description": suite.description},
            "cases": rows,
        }
        body, media = json.dumps(payload, indent=2, ensure_ascii=False), "application/json"
    else:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow(
                r | {"steps": steps_to_text(r["steps"]), "tags": ", ".join(r["tags"]),
                     "automation_key": r["automation_key"] or ""}
            )
        body, media = buf.getvalue(), "text/csv; charset=utf-8"
    return Response(
        body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{_filename(suite, format)}"'},
    )


# --- Import --------------------------------------------------------------------------


def _parse_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "title" not in [f.strip().lower() for f in reader.fieldnames]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CSV must have a header row with a 'title' column")
    rows = []
    for raw in reader:
        r = {(k or "").strip().lower(): (v or "") for k, v in raw.items()}
        rows.append(
            {
                "id": r.get("id", ""),
                "section_path": r.get("section_path", ""),
                "title": r.get("title", "").strip(),
                "preconditions": r.get("preconditions", ""),
                "steps": text_to_steps(r.get("steps", "")),
                "expected_result": r.get("expected_result", ""),
                "priority": r.get("priority", "").strip().lower() or None,
                "type": r.get("type", "").strip().lower() or None,
                "tags": [t for t in r.get("tags", "").split(",")],
                "automation_status": r.get("automation_status", "").strip().lower() or None,
                "automation_key": r.get("automation_key", ""),
            }
        )
    return rows


def _parse_json(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid JSON: {e}") from e
    cases = data.get("cases") if isinstance(data, dict) else data
    if not isinstance(cases, list) or not all(isinstance(c, dict) for c in cases):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "JSON must be a list of cases or {\"cases\": [...]}")
    return cases


async def _ensure_section(
    session: AsyncSession,
    suite_id: int,
    path: str,
    by_path: dict[tuple[str, ...], int],
    result: ImportResult,
) -> int:
    parts = tuple(p for p in _PATH_SEP.split(path.strip()) if p) or ("Imported",)
    parent_id: int | None = None
    for depth in range(1, len(parts) + 1):
        key = tuple(p.lower() for p in parts[:depth])
        if key not in by_path:
            siblings = [k for k in by_path if len(k) == depth and k[:-1] == key[:-1]]
            sec = Section(suite_id=suite_id, parent_id=parent_id, name=parts[depth - 1][:200],
                          position=len(siblings))
            session.add(sec)
            await session.flush()
            by_path[key] = sec.id
            result.sections_created += 1
        parent_id = by_path[key]
    assert parent_id is not None
    return parent_id


@router.post("/suites/{suite_id}/import", response_model=ImportResult)
async def import_suite(
    suite_id: int,
    file: UploadFile,
    session: Session,
    format: Annotated[Literal["csv", "json"] | None, Query(description="Defaults to file extension")] = None,
) -> ImportResult:
    suite = await get_or_404(session, Suite, suite_id)
    raw = await file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large (max 20 MB)")
    text = raw.decode("utf-8-sig", errors="replace")
    fmt = format or ("json" if (file.filename or "").lower().endswith(".json")
                     or text.lstrip().startswith(("{", "[")) else "csv")
    rows = _parse_json(text) if fmt == "json" else _parse_csv(text)

    sections = await suite_sections(session, suite.id)
    paths = section_paths(sections)
    by_path = {tuple(p.lower() for p in _PATH_SEP.split(path)): sid for sid, path in paths.items()}
    existing = {c.id: c for c in await session.scalars(select(TestCase).where(TestCase.suite_id == suite.id))}
    keys = {
        k: cid
        for cid, k in await session.execute(
            select(TestCase.id, TestCase.automation_key).where(
                TestCase.project_id == suite.project_id, TestCase.automation_key.is_not(None)
            )
        )
    }
    next_pos: dict[int, int] = {}
    for c in existing.values():
        next_pos[c.section_id] = max(next_pos.get(c.section_id, 0), c.position + 1)

    result = ImportResult()
    for n, row in enumerate(rows, start=2 if fmt == "csv" else 1):
        label = f"row {n}" if fmt == "csv" else f"case #{n}"
        fields = {k: v for k, v in row.items() if k in CaseFields.model_fields and v is not None}
        try:
            data = CaseFields.model_validate(fields)
        except ValidationError as e:
            err = e.errors()[0]
            result.errors.append(f"{label}: {'.'.join(map(str, err['loc']))}: {err['msg']}")
            continue

        m = CASE_REF.match(str(row.get("id") or "").strip())
        case = existing.get(int(m.group(1))) if m else None
        owner = keys.get(data.automation_key) if data.automation_key else None
        if owner is not None and owner != (case.id if case else None):
            result.errors.append(
                f"{label}: automation_key {data.automation_key!r} is already used by C{owner}"
            )
            continue

        section_id = (
            await _ensure_section(session, suite.id, row["section_path"], by_path, result)
            if row.get("section_path") or case is None
            else case.section_id
        )
        if case is not None:
            # Only overwrite fields present in the input; blank enum cells keep current values.
            if case.automation_key and "automation_key" in data.model_fields_set:
                keys.pop(case.automation_key, None)
            for k, v in data.model_dump(mode="json", exclude_unset=True).items():
                setattr(case, k, v)
            if case.section_id != section_id:
                case.section_id = section_id
                case.position = next_pos.get(section_id, 0)
                next_pos[section_id] = case.position + 1
            result.updated += 1
        else:
            case = TestCase(project_id=suite.project_id, suite_id=suite.id, section_id=section_id,
                            position=next_pos.get(section_id, 0), **data.model_dump(mode="json"))
            next_pos[section_id] = case.position + 1
            session.add(case)
            await session.flush()
            existing[case.id] = case
            result.created += 1
        if case.automation_key:
            keys[case.automation_key] = case.id

    await session.commit()
    return result
