"""Shared query helpers used by several routers."""

from __future__ import annotations

import re
from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Base, Section, TestCase
from app.schemas import CaseFilter

M = TypeVar("M", bound=Base)

CASE_REF = re.compile(r"^[Cc]?(\d+)$")


async def get_or_404(session: AsyncSession, model: type[M], obj_id: int) -> M:
    obj = await session.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} {obj_id} not found")
    return obj


def parse_case_ref(ref: str | int) -> int:
    """Accept 142, "142" or "C142"."""
    m = CASE_REF.match(str(ref).strip())
    if not m:
        raise HTTPException(422, f"Invalid case id {ref!r}")
    return int(m.group(1))


async def commit_or_409(session: AsyncSession) -> None:
    """Commit, translating constraint violations into a readable 409."""
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        msg = str(e.orig)
        if "uq_test_cases_project_automation_key" in msg:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Another case in this project already has this automation_key"
            ) from e
        raise HTTPException(status.HTTP_409_CONFLICT, "Conflict with existing data") from e


async def suite_sections(session: AsyncSession, suite_id: int) -> list[Section]:
    rows = await session.scalars(
        select(Section).where(Section.suite_id == suite_id).order_by(Section.position, Section.id)
    )
    return list(rows)


def descendant_ids(sections: list[Section], root_id: int) -> set[int]:
    """root_id plus all its descendants."""
    children: dict[int | None, list[int]] = {}
    for s in sections:
        children.setdefault(s.parent_id, []).append(s.id)
    out, stack = set(), [root_id]
    while stack:
        sid = stack.pop()
        if sid in out:
            continue
        out.add(sid)
        stack.extend(children.get(sid, []))
    return out


def section_paths(sections: list[Section]) -> dict[int, str]:
    """section id -> "Parent > Child" path."""
    by_id = {s.id: s for s in sections}
    cache: dict[int, str] = {}

    def path(sid: int) -> str:
        if sid not in cache:
            s = by_id[sid]
            cache[sid] = s.name if s.parent_id is None else f"{path(s.parent_id)} > {s.name}"
        return cache[sid]

    return {s.id: path(s.id) for s in sections}


def tree_order(sections: list[Section]) -> list[int]:
    """Section ids in depth-first display order."""
    children: dict[int | None, list[Section]] = {}
    for s in sections:
        children.setdefault(s.parent_id, []).append(s)
    out: list[int] = []

    def walk(pid: int | None) -> None:
        for s in sorted(children.get(pid, []), key=lambda x: (x.position, x.id)):
            out.append(s.id)
            walk(s.id)

    walk(None)
    return out


async def next_case_position(session: AsyncSession, section_id: int) -> int:
    cur = await session.scalar(
        select(func.max(TestCase.position)).where(TestCase.section_id == section_id)
    )
    return 0 if cur is None else cur + 1


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def filtered_cases_query(
    session: AsyncSession, project_id: int, f: CaseFilter
) -> Select[tuple[TestCase]]:
    stmt = select(TestCase).where(TestCase.project_id == project_id)
    if f.suite_id is not None:
        stmt = stmt.where(TestCase.suite_id == f.suite_id)
    if f.section_id is not None:
        if f.include_subsections:
            section = await get_or_404(session, Section, f.section_id)
            ids = descendant_ids(await suite_sections(session, section.suite_id), section.id)
            stmt = stmt.where(TestCase.section_id.in_(ids))
        else:
            stmt = stmt.where(TestCase.section_id == f.section_id)
    if f.q and f.q.strip():
        q = f.q.strip()
        cond = TestCase.title.ilike(f"%{_escape_like(q)}%", escape="\\")
        m = CASE_REF.match(q)
        if m:
            cond = or_(cond, TestCase.id == int(m.group(1)))
        stmt = stmt.where(cond)
    if f.tags:
        stmt = stmt.where(TestCase.tags.contains([t.strip().lower() for t in f.tags]))
    if f.priority:
        stmt = stmt.where(TestCase.priority.in_(f.priority))
    if f.type:
        stmt = stmt.where(TestCase.type.in_(f.type))
    if f.automation_status:
        stmt = stmt.where(TestCase.automation_status.in_(f.automation_status))
    return stmt
