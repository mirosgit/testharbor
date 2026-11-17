"""Shared query helpers used by several routers."""

from __future__ import annotations

import re
from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Base, RunCase, Section, TestCase, TestResult, TestRun
from app.schemas import CaseFilter, ResultIn, RunSelection, RunStats

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


# --- Runs ----------------------------------------------------------------------------


async def resolve_selection(session: AsyncSession, project_id: int, sel: RunSelection) -> list[int]:
    """Case ids in the project matched by any of the selectors (union)."""
    ids: set[int] = set()
    if sel.case_ids:
        found = set(
            await session.scalars(
                select(TestCase.id).where(
                    TestCase.id.in_(sel.case_ids), TestCase.project_id == project_id
                )
            )
        )
        missing = sorted(set(sel.case_ids) - found)
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Cases not found in this project: {', '.join(f'C{i}' for i in missing)}",
            )
        ids |= found
    if sel.suite_id is not None:
        ids |= set(
            await session.scalars(
                select(TestCase.id).where(
                    TestCase.suite_id == sel.suite_id, TestCase.project_id == project_id
                )
            )
        )
    for section_id in sel.section_ids:
        f = CaseFilter(section_id=section_id, include_subsections=True)
        stmt = await filtered_cases_query(session, project_id, f)
        ids |= set(await session.scalars(stmt.with_only_columns(TestCase.id)))
    if sel.filter is not None:
        stmt = await filtered_cases_query(session, project_id, sel.filter)
        ids |= set(await session.scalars(stmt.with_only_columns(TestCase.id)))
    return sorted(ids)


async def add_cases_to_run(session: AsyncSession, run_id: int, case_ids: list[int]) -> int:
    """Add memberships (ignoring ones that exist). Returns how many were new."""
    if not case_ids:
        return 0
    stmt = (
        pg_insert(RunCase)
        .values([{"run_id": run_id, "case_id": cid} for cid in case_ids])
        .on_conflict_do_nothing()
        .returning(RunCase.case_id)
    )
    return len((await session.execute(stmt)).all())


async def record_result(
    session: AsyncSession, run_id: int, data: ResultIn, user_id: int | None = None
) -> TestResult:
    """Append a result and make it the case's current status in the run."""
    result = TestResult(run_id=run_id, user_id=user_id, **data.model_dump())
    session.add(result)
    stmt = pg_insert(RunCase).values(run_id=run_id, case_id=data.case_id, status=data.status)
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[RunCase.run_id, RunCase.case_id],
            set_={"status": stmt.excluded.status, "updated_at": func.now()},
        )
    )
    await session.flush()
    return result


async def run_stats(session: AsyncSession, run_ids: list[int]) -> dict[int, RunStats]:
    out = {rid: RunStats() for rid in run_ids}
    if not run_ids:
        return out
    rows = await session.execute(
        select(RunCase.run_id, RunCase.status, func.count())
        .where(RunCase.run_id.in_(run_ids))
        .group_by(RunCase.run_id, RunCase.status)
    )
    for rid, st, n in rows:
        stats = out[rid]
        setattr(stats, st.value, n)
        stats.total += n
    return out


def ensure_open(run: TestRun) -> None:
    if run.closed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Run is closed; reopen it to change results")
