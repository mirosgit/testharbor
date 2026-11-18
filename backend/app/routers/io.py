"""Import / export of a suite's cases as CSV or JSON.

Export CSV columns: id, external_id, section_path, title, description, preconditions, steps, expected_result,
priority, type, tags, automation_status, automation_key, state, owner, automation_complexity,
automation_progress, sprint, roles, created_at, updated_at, updated_by, then one column per
custom field.

- section_path: "Parent > Child". Missing sections are created on import.
- steps: one cell, numbered lines "1. action => expected".
- tags, roles: comma-separated.

Import also understands BrowserStack Test Management and TestRail CSV exports (see
app/case_import.py): `Folder Path` / `Section Hierarchy` become sections, their own ids
(e.g. "TC-770") are kept as `external_id` so re-importing updates instead of duplicating.

JSON is lossless: {"format": "testharbor", "version": 1, "suite": {...}, "cases": [...]}.
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

from app.auth import CurrentPrincipal
from app.case_import import parse_csv, parse_datetime, steps_to_text, text_to_steps  # noqa: F401
from app.db import get_session
from app.models import Section, Suite, TestCase
from app.schemas import CaseFields, ExtraColumn, ImportResult
from app.services import CASE_REF, get_or_404, remember_roles, section_paths, suite_sections, tree_order

router = APIRouter(prefix="/api", tags=["import/export"])
Session = Annotated[AsyncSession, Depends(get_session)]

CSV_COLUMNS = [
    "id", "external_id", "section_path", "title", "description", "preconditions", "steps", "expected_result",
    "priority", "type", "tags", "automation_status", "automation_key", "state", "owner",
    "automation_complexity", "automation_progress", "sprint", "roles", "created_at", "updated_at",
    "updated_by",
]
_PATH_SEP = re.compile(r"\s*[>›]\s*")
MAX_IMPORT_BYTES = 20 * 1024 * 1024
DEFAULT_SECTION = "Imported"


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
            "external_id": c.external_id,
            "section_path": paths[c.section_id],
            "title": c.title,
            "description": c.description,
            "preconditions": c.preconditions,
            "steps": c.steps,
            "expected_result": c.expected_result,
            "priority": c.priority.value,
            "type": c.type.value,
            "tags": c.tags,
            "automation_status": c.automation_status.value,
            "automation_key": c.automation_key,
            "state": c.state.value,
            "owner": c.owner,
            "automation_complexity": c.automation_complexity.value if c.automation_complexity else None,
            "automation_progress": c.automation_progress.value if c.automation_progress else None,
            "sprint": c.sprint,
            "roles": c.roles,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
            "updated_by": c.updated_by,
            "custom_fields": c.custom_fields,
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
        # Custom fields become extra columns (first-seen order) after the built-in ones.
        extra: dict[str, None] = {}
        for r in rows:
            for f in r["custom_fields"]:
                if f["name"] not in CSV_COLUMNS:
                    extra.setdefault(f["name"], None)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS + list(extra))
        writer.writeheader()
        for r in rows:
            values = {f["name"]: f["value"] for f in r.pop("custom_fields")}
            writer.writerow(
                {k: ("" if v is None else v) for k, v in r.items()}
                | {"steps": steps_to_text(r["steps"]), "tags": ", ".join(r["tags"]),
                   "roles": ", ".join(r["roles"])}
                | {name: values.get(name, "") for name in extra}
            )
        body, media = buf.getvalue(), "text/csv; charset=utf-8"
    return Response(
        body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{_filename(suite, format)}"'},
    )


# --- Import --------------------------------------------------------------------------


def _parse_json(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid JSON: {e}") from e
    cases = data.get("cases") if isinstance(data, dict) else data
    if not isinstance(cases, list) or not all(isinstance(c, dict) for c in cases):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "JSON must be a list of cases or {\"cases\": [...]}")
    return cases


def _split_path(path: str) -> tuple[str, ...]:
    return tuple(p.strip()[:200] for p in _PATH_SEP.split(path or "") if p.strip())


class _Tree:
    """Sections of a suite by lowercased path, creating missing ones on demand."""

    def __init__(self, session: AsyncSession, suite_id: int, sections: list[Section], result: ImportResult):
        self.session, self.suite_id, self.result = session, suite_id, result
        by_id = {s.id: s for s in sections}
        self.path_of: dict[int, tuple[str, ...]] = {}
        for s in sections:  # walk the parent chain (names may contain any characters)
            parts, cur = [], s
            while cur is not None:
                parts.insert(0, cur.name)
                cur = by_id.get(cur.parent_id) if cur.parent_id is not None else None
            self.path_of[s.id] = tuple(parts)
        self.by_path = {tuple(p.lower() for p in parts): sid for sid, parts in self.path_of.items()}

    async def ensure(self, parts: tuple[str, ...]) -> int:
        parent_id: int | None = None
        for depth in range(1, len(parts) + 1):
            key = tuple(p.lower() for p in parts[:depth])
            if key not in self.by_path:
                siblings = [k for k in self.by_path if len(k) == depth and k[:-1] == key[:-1]]
                sec = Section(suite_id=self.suite_id, parent_id=parent_id, name=parts[depth - 1],
                              position=len(siblings))
                self.session.add(sec)
                await self.session.flush()
                self.by_path[key] = sec.id
                self.path_of[sec.id] = parts[:depth]
                self.result.sections_created += 1
            parent_id = self.by_path[key]
        assert parent_id is not None
        return parent_id


@router.post("/suites/{suite_id}/import", response_model=ImportResult)
async def import_suite(
    suite_id: int,
    file: UploadFile,
    session: Session,
    principal: CurrentPrincipal,
    format: Annotated[Literal["csv", "json"] | None, Query(description="Defaults to file extension")] = None,
    section_id: Annotated[int | None, Query(description="Import into this existing section")] = None,
    new_section: Annotated[str | None, Query(max_length=200, description="Import into a top-level section with this name (created if missing)")] = None,
    keep_paths: Annotated[bool, Query(description="Recreate the file's folders (section_path / Folder Path) inside the target")] = True,
    columns: Annotated[list[str] | None, Query(description="CSV: extra columns to keep as custom fields (default: all but tool-internal ones; pass an empty value for none)")] = None,
    dry_run: Annotated[bool, Query(description="Analyse the file and report what would happen, without saving")] = False,
) -> ImportResult:
    """Import cases from CSV (TestHarbor, BrowserStack or TestRail export) or JSON.

    Target: `section_id` or `new_section`; with neither, folders from the file go to the suite's
    top level and cases without a folder go to an "Imported" section.
    """
    suite = await get_or_404(session, Suite, suite_id)
    raw = await file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large (max 20 MB)")
    text = raw.decode("utf-8-sig", errors="replace")
    fmt = format or ("json" if (file.filename or "").lower().endswith(".json")
                     or text.lstrip().startswith(("{", "[")) else "csv")

    result = ImportResult(dry_run=dry_run)
    if fmt == "json":
        rows, own_format = _parse_json(text), True
    else:
        try:
            parsed = parse_csv(text, {c for c in columns if c.strip()} if columns is not None else None)
        except (ValueError, csv.Error) as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Can't read CSV: {e}") from e
        rows, own_format = parsed.rows, parsed.own_format
        result.ignored_columns, result.warnings = parsed.ignored_columns, parsed.warnings
        result.extra_columns = [ExtraColumn(name=n, selected=s) for n, s in parsed.extra_columns]

    sections = await suite_sections(session, suite.id)
    tree = _Tree(session, suite.id, sections, result)

    # Where cases go.
    target: tuple[str, ...] = ()
    if section_id is not None:
        if section_id not in tree.path_of:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Section not found in this suite")
        target = tree.path_of[section_id]
    elif new_section and new_section.strip():
        target = (new_section.strip()[:200],)  # one top-level section, name taken literally
        await tree.ensure(target)
    if target:
        result.section_id = tree.by_path[tuple(p.lower() for p in target)]

    existing = {c.id: c for c in await session.scalars(select(TestCase).where(TestCase.suite_id == suite.id))}
    by_external = {c.external_id: c for c in existing.values() if c.external_id}
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

    for n, row in enumerate(rows, start=1):
        label = f"row {row.get('_line', n + 1)}" if fmt == "csv" else f"case #{n}"
        fields = {k: v for k, v in row.items() if k in CaseFields.model_fields and v is not None}
        try:
            data = CaseFields.model_validate(fields)
        except ValidationError as e:
            err = e.errors()[0]
            result.errors.append(f"{label}: {'.'.join(map(str, err['loc']))}: {err['msg']}")
            continue

        case = None
        if own_format and (m := CASE_REF.match(str(row.get("id") or "").strip())):
            case = existing.get(int(m.group(1)))
        if case is None and data.external_id:
            case = by_external.get(data.external_id)

        owner = keys.get(data.automation_key) if data.automation_key else None
        if owner is not None and owner != (case.id if case else None):
            result.errors.append(f"{label}: automation_key {data.automation_key!r} is already used by C{owner}")
            continue

        # Section: file folder (inside the target), else the target, else keep / "Imported".
        file_path = _split_path(str(row.get("section_path") or "")) if keep_paths else ()
        if file_path or target:
            section = await tree.ensure(target + file_path)
        elif case is not None:
            section = case.section_id
        else:
            section = await tree.ensure((DEFAULT_SECTION,))

        if case is not None:
            if case.automation_key and "automation_key" in data.model_fields_set:
                keys.pop(case.automation_key, None)
            values = data.model_dump(mode="json", exclude_unset=True)
            if "custom_fields" in values:
                # Merge: imported fields replace same-named ones, other fields are kept.
                incoming = {f["name"].lower(): f for f in values.pop("custom_fields")}
                merged = [incoming.pop(f["name"].lower(), f) for f in case.custom_fields]
                values["custom_fields"] = merged + list(incoming.values())
            for k, v in values.items():
                setattr(case, k, v)
            if case.section_id != section:
                case.section_id = section
                case.position = next_pos.get(section, 0)
                next_pos[section] = case.position + 1
            result.updated += 1
        else:
            case = TestCase(project_id=suite.project_id, suite_id=suite.id, section_id=section,
                            position=next_pos.get(section, 0), **data.model_dump(mode="json"))
            next_pos[section] = case.position + 1
            session.add(case)
            await session.flush()
            existing[case.id] = case
            result.created += 1
        # Keep the original dates / editor from the file; otherwise the importer edited it.
        for k in ("created_at", "updated_at"):
            when = row.get(k)
            if isinstance(when, str):
                when, warning = parse_datetime(when)
                if warning:
                    result.warnings.append(f"{label}: {warning}")
            if when:
                setattr(case, k, when)
        case.updated_by = " ".join(str(row.get("updated_by") or "").split())[:200] or principal.user.name
        if case.automation_key:
            keys[case.automation_key] = case.id
        if case.external_id:
            by_external[case.external_id] = case

    # New roles join the project's Applicable Roles list; spellings of one role are unified
    # ("admin" -> "Admin", "Super Admin" -> "Super Admin (SA)").
    await remember_roles(session, suite.project_id, [r for c in existing.values() for r in c.roles])
    if dry_run:
        await session.rollback()
    else:
        await session.commit()
    return result
