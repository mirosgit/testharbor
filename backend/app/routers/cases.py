from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import AutomationStatus, CaseType, Priority, Project, Section, Suite, TestCase
from app.schemas import CaseFilter, CaseIn, CaseList, CaseMoveIn, CaseOut, CasePatch
from app.services import (
    commit_or_409,
    filtered_cases_query,
    get_or_404,
    next_case_position,
    parse_case_ref,
)

router = APIRouter(prefix="/api", tags=["cases"])
Session = Annotated[AsyncSession, Depends(get_session)]


def _split(values: list[str] | None) -> list[str]:
    """Accept both ?tags=a&tags=b and ?tags=a,b."""
    out: list[str] = []
    for v in values or []:
        out.extend(p.strip() for p in v.split(",") if p.strip())
    return out


def case_filter_params(
    suite_id: int | None = None,
    section_id: int | None = None,
    include_subsections: bool = True,
    q: Annotated[str | None, Query(description="Title substring, or a case id like C142")] = None,
    tags: Annotated[list[str] | None, Query(description="Cases must have all of these tags")] = None,
    priority: Annotated[list[str] | None, Query()] = None,
    type: Annotated[list[str] | None, Query()] = None,
    automation_status: Annotated[list[str] | None, Query()] = None,
) -> CaseFilter:
    try:
        return CaseFilter(
            suite_id=suite_id,
            section_id=section_id,
            include_subsections=include_subsections,
            q=q,
            tags=_split(tags),
            priority=[Priority(p) for p in _split(priority)],
            type=[CaseType(t) for t in _split(type)],
            automation_status=[AutomationStatus(a) for a in _split(automation_status)],
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/projects/{project_id}/cases", response_model=CaseList)
async def list_cases(
    project_id: int,
    session: Session,
    f: Annotated[CaseFilter, Depends(case_filter_params)],
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CaseList:
    await get_or_404(session, Project, project_id)
    stmt = await filtered_cases_query(session, project_id, f)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = await session.scalars(
        stmt.order_by(TestCase.suite_id, TestCase.section_id, TestCase.position, TestCase.id)
        .limit(limit)
        .offset(offset)
    )
    return CaseList(items=[CaseOut.model_validate(c) for c in rows], total=total or 0)


@router.get("/projects/{project_id}/tags", response_model=list[str])
async def list_tags(project_id: int, session: Session) -> list[str]:
    """All distinct tags used in the project (for autocomplete)."""
    tag = func.unnest(TestCase.tags).label("tag")
    sub = select(tag).where(TestCase.project_id == project_id).subquery()
    rows = await session.scalars(select(sub.c.tag).distinct().order_by(sub.c.tag))
    return list(rows)


@router.post("/cases", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
async def create_case(body: CaseIn, session: Session) -> TestCase:
    section = await get_or_404(session, Section, body.section_id)
    suite = await get_or_404(session, Suite, section.suite_id)
    case = TestCase(
        project_id=suite.project_id,
        suite_id=suite.id,
        position=await next_case_position(session, section.id),
        **body.model_dump(mode="json"),
    )
    session.add(case)
    await commit_or_409(session)
    return case


@router.get("/cases/{case_ref}", response_model=CaseOut)
async def get_case(case_ref: str, session: Session) -> TestCase:
    return await get_or_404(session, TestCase, parse_case_ref(case_ref))


@router.patch("/cases/{case_ref}", response_model=CaseOut)
async def update_case(case_ref: str, body: CasePatch, session: Session) -> TestCase:
    case = await get_or_404(session, TestCase, parse_case_ref(case_ref))
    data = body.model_dump(mode="json", exclude_unset=True)
    # automation_key may be explicitly cleared with null; other fields ignore nulls.
    data = {k: v for k, v in data.items() if v is not None or k in ("automation_key", "external_id")}
    section_id = data.pop("section_id", None)
    if section_id is not None and section_id != case.section_id:
        await _move(session, [case], section_id, None)
    for k, v in data.items():
        setattr(case, k, v)
    await commit_or_409(session)
    return case


@router.delete("/cases/{case_ref}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(case_ref: str, session: Session) -> None:
    case = await get_or_404(session, TestCase, parse_case_ref(case_ref))
    await session.delete(case)
    await session.commit()


async def _move(
    session: AsyncSession, cases: list[TestCase], section_id: int, position: int | None
) -> None:
    target = await get_or_404(session, Section, section_id)
    suite = await get_or_404(session, Suite, target.suite_id)
    if any(c.project_id != suite.project_id for c in cases):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cases can only be moved within their project")
    moving_ids = {c.id for c in cases}
    existing = list(
        await session.scalars(
            select(TestCase)
            .where(TestCase.section_id == section_id, TestCase.id.not_in(moving_ids))
            .order_by(TestCase.position, TestCase.id)
        )
    )
    idx = len(existing) if position is None else max(0, min(position, len(existing)))
    ordered = existing[:idx] + cases + existing[idx:]
    for i, c in enumerate(ordered):
        c.position = i
    for c in cases:
        c.section_id = section_id
        c.suite_id = suite.id


@router.post("/cases/move", response_model=list[CaseOut])
async def move_cases(body: CaseMoveIn, session: Session) -> list[TestCase]:
    """Move cases (in the given order) into a section, inserted at `position`."""
    found = {
        c.id: c for c in await session.scalars(select(TestCase).where(TestCase.id.in_(body.case_ids)))
    }
    missing = [i for i in body.case_ids if i not in found]
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Cases not found: {missing}")
    cases = [found[i] for i in dict.fromkeys(body.case_ids)]
    await _move(session, cases, body.section_id, body.position)
    await session.commit()
    return cases
