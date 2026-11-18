import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Integer, case, cast, func, literal, select, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.db import get_session
from app.models import (
    AutomationComplexity,
    AutomationProgress,
    AutomationStatus,
    CaseState,
    CaseType,
    Priority,
    Project,
    Section,
    Suite,
    TestCase,
    User,
)
from app.schemas import (
    CLEARABLE_FIELDS,
    BulkResult,
    CaseBulkUpdate,
    CaseFilter,
    CaseIn,
    CaseList,
    CaseMoveIn,
    CaseOut,
    CasePatch,
    CaseValues,
    FieldValues,
)
from app.services import (
    commit_or_409,
    filtered_cases_query,
    get_or_404,
    next_case_position,
    parse_case_ref,
    remember_roles,
    tree_order,
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
    state: Annotated[list[str] | None, Query()] = None,
    automation_complexity: Annotated[list[str] | None, Query()] = None,
    automation_progress: Annotated[list[str] | None, Query()] = None,
    owner: Annotated[list[str] | None, Query(description="Any of these owners (repeat, no comma splitting)")] = None,
    sprint: Annotated[list[str] | None, Query(description="Any of these sprints (repeat)")] = None,
    role: Annotated[list[str] | None, Query(description="Cases for any of these roles (repeat)")] = None,
    field: Annotated[
        list[str] | None, Query(description='Custom field filter "Name=Value"; repeat for more')
    ] = None,
) -> CaseFilter:
    fields: dict[str, list[str]] = {}
    for item in field or []:
        name, sep, value = item.partition("=")
        if not sep or not name.strip():
            raise HTTPException(422, f"field filter must look like Name=Value, got {item!r}")
        fields.setdefault(" ".join(name.split()), []).append(value.strip())
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
            state=[CaseState(x) for x in _split(state)],
            automation_complexity=[AutomationComplexity(x) for x in _split(automation_complexity)],
            automation_progress=[AutomationProgress(x) for x in _split(automation_progress)],
            # Free-text values may contain commas, so these are not split.
            owner=[x.strip() for x in owner or [] if x.strip()],
            sprint=[x.strip() for x in sprint or [] if x.strip()],
            roles=[x.strip() for x in role or [] if x.strip()],
            fields=fields,
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


def _rank(column, members):  # type: ignore[no-untyped-def]
    return case({m: i for i, m in enumerate(members)}, value=column)


# Sort keys for the case list. Within a section; sections stay in tree order.
CASE_SORTS = {
    "id": lambda: [TestCase.id],
    "title": lambda: [func.lower(TestCase.title)],
    "priority": lambda: [_rank(TestCase.priority, list(Priority))],  # asc: low -> critical
    "type": lambda: [_rank(TestCase.type, list(CaseType))],
    "state": lambda: [_rank(TestCase.state, list(CaseState))],
    "automation_status": lambda: [_rank(TestCase.automation_status, list(AutomationStatus))],
    "owner": lambda: [func.lower(TestCase.owner)],
    # Natural order: "Sprint 9" before "Sprint 10".
    "sprint": lambda: [
        func.lower(func.regexp_replace(TestCase.sprint, r"\d+", "", "g")),
        cast(func.substring(TestCase.sprint, r"(\d+)"), Integer),
    ],
    "created_at": lambda: [TestCase.created_at],
    "updated_at": lambda: [TestCase.updated_at],
}
CaseSort = Literal["manual", "id", "title", "priority", "type", "state", "automation_status", "owner",
                   "sprint", "created_at", "updated_at"]


@router.get("/projects/{project_id}/cases", response_model=CaseList)
async def list_cases(
    project_id: int,
    session: Session,
    f: Annotated[CaseFilter, Depends(case_filter_params)],
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: Annotated[CaseSort, Query(description="Order within each section; manual = drag-and-drop order")] = "manual",
    order: Literal["asc", "desc"] = "asc",
) -> CaseList:
    """Cases grouped by suite and section (in tree order), sorted within each section."""
    await get_or_404(session, Project, project_id)
    stmt = await filtered_cases_query(session, project_id, f)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))

    suite_ids = (
        [f.suite_id] if f.suite_id is not None
        else list(await session.scalars(select(Suite.id).where(Suite.project_id == project_id)))
    )
    sections = list(await session.scalars(select(Section).where(Section.suite_id.in_(suite_ids))))
    section_order = literal(tree_order(sections), ARRAY(Integer))
    keys = []
    if sort != "manual":
        for k in CASE_SORTS[sort]():
            keys.append((k.desc() if order == "desc" else k.asc()).nulls_last())
    rows = await session.scalars(
        stmt.order_by(
            TestCase.suite_id,
            func.array_position(section_order, TestCase.section_id),
            *keys,
            TestCase.position,
            TestCase.id,
        )
        .limit(limit)
        .offset(offset)
    )
    return CaseList(items=[CaseOut.model_validate(c) for c in rows], total=total or 0)


@router.get("/projects/{project_id}/custom-fields", response_model=list[FieldValues])
async def list_custom_fields(project_id: int, session: Session) -> list[FieldValues]:
    """Custom field names used in the project with their distinct values (for filters/autocomplete)."""
    rows = await session.execute(
        text(
            "SELECT f->>'name' AS name, f->>'value' AS value FROM test_cases, "
            "jsonb_array_elements(custom_fields) AS f WHERE project_id = :p "
            "GROUP BY 1, 2 ORDER BY 1, 2"
        ),
        {"p": project_id},
    )
    out: dict[str, list[str]] = {}
    for name, value in rows:
        values = out.setdefault(name, [])
        if len(values) < 300:
            values.append(value)
    return [FieldValues(name=n, values=v) for n, v in out.items()]


@router.get("/projects/{project_id}/case-values", response_model=CaseValues)
async def list_case_values(project_id: int, session: Session) -> CaseValues:
    """Owners, sprints and roles for pickers. Owners include active users; roles are the
    project's list, then any other roles found on cases."""
    project = await get_or_404(session, Project, project_id)
    in_project = TestCase.project_id == project_id
    owners = set(await session.scalars(select(TestCase.owner).where(in_project, TestCase.owner.is_not(None)).distinct()))
    owners |= set(await session.scalars(select(User.name).where(User.is_active)))
    sprints = await session.scalars(select(TestCase.sprint).where(in_project, TestCase.sprint.is_not(None)).distinct())
    role = func.unnest(TestCase.roles).label("role")
    sub = select(role).where(in_project).subquery()
    used = await session.scalars(select(sub.c.role).distinct())
    listed = {r.lower() for r in project.roles}
    extra = sorted((r for r in used if r.lower() not in listed), key=str.lower)

    def natural(v: str) -> list[object]:  # "Sprint 9" before "Sprint 10"
        return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", v)]

    return CaseValues(
        owners=sorted(owners, key=str.lower),
        sprints=sorted(sprints, key=natural),
        roles=[*project.roles, *extra],
    )


@router.get("/projects/{project_id}/tags", response_model=list[str])
async def list_tags(project_id: int, session: Session) -> list[str]:
    """All distinct tags used in the project (for autocomplete)."""
    tag = func.unnest(TestCase.tags).label("tag")
    sub = select(tag).where(TestCase.project_id == project_id).subquery()
    rows = await session.scalars(select(sub.c.tag).distinct().order_by(sub.c.tag))
    return list(rows)


@router.post("/cases", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
async def create_case(body: CaseIn, session: Session, principal: CurrentPrincipal) -> TestCase:
    section = await get_or_404(session, Section, body.section_id)
    suite = await get_or_404(session, Suite, section.suite_id)
    case = TestCase(
        project_id=suite.project_id,
        suite_id=suite.id,
        position=await next_case_position(session, section.id),
        updated_by=principal.user.name,
        **body.model_dump(mode="json"),
    )
    session.add(case)
    await remember_roles(session, case.project_id, case.roles)
    await commit_or_409(session)
    return case


@router.post("/cases/bulk-update", response_model=BulkResult)
async def bulk_update_cases(body: CaseBulkUpdate, session: Session, principal: CurrentPrincipal) -> BulkResult:
    """Change fields of many cases at once (all must be in one project)."""
    cases = list(await session.scalars(select(TestCase).where(TestCase.id.in_(body.case_ids))))
    missing = sorted(set(body.case_ids) - {c.id for c in cases})
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Cases not found: {', '.join(f'C{i}' for i in missing)}")
    projects = {c.project_id for c in cases}
    if len(projects) != 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cases must belong to one project")

    values = body.set.model_dump(mode="json", exclude_unset=True)
    values = {k: v for k, v in values.items() if v is not None or k in CLEARABLE_FIELDS}
    drop_tags = set(body.remove_tags)
    drop_roles = {r.lower() for r in body.remove_roles}
    for c in cases:
        for k, v in values.items():
            setattr(c, k, v)
        if body.add_tags or drop_tags:
            c.tags = [t for t in dict.fromkeys([*c.tags, *body.add_tags]) if t not in drop_tags]
        if body.add_roles or drop_roles:
            have = {r.lower() for r in c.roles}
            merged = [*c.roles, *(r for r in body.add_roles if r.lower() not in have)]
            c.roles = [r for r in merged if r.lower() not in drop_roles]
        if session.is_modified(c):
            c.updated_by = principal.user.name
    await remember_roles(session, projects.pop(), body.add_roles)
    await session.commit()
    return BulkResult(updated=len(cases))


@router.get("/cases/{case_ref}", response_model=CaseOut)
async def get_case(case_ref: str, session: Session) -> TestCase:
    return await get_or_404(session, TestCase, parse_case_ref(case_ref))


@router.patch("/cases/{case_ref}", response_model=CaseOut)
async def update_case(
    case_ref: str, body: CasePatch, session: Session, principal: CurrentPrincipal
) -> TestCase:
    case = await get_or_404(session, TestCase, parse_case_ref(case_ref))
    data = body.model_dump(mode="json", exclude_unset=True)
    # Optional fields may be explicitly cleared with null; other fields ignore nulls.
    data = {k: v for k, v in data.items() if v is not None or k in CLEARABLE_FIELDS}
    section_id = data.pop("section_id", None)
    if section_id is not None and section_id != case.section_id:
        await _move(session, [case], section_id, None)
    for k, v in data.items():
        setattr(case, k, v)
    if session.is_modified(case):
        case.updated_by = principal.user.name
    if "roles" in data:
        await remember_roles(session, case.project_id, case.roles)
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
