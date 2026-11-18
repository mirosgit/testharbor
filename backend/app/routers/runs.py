from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.db import get_session
from app.models import (
    Project,
    ResultStatus,
    RunCase,
    RunSource,
    Section,
    TestCase,
    TestResult,
    TestRun,
    User,
)
from app.schemas import (
    BulkResultsIn,
    CaseHistoryItem,
    ResultIn,
    ResultOut,
    RunCaseOut,
    RunIn,
    RunList,
    RunOut,
    RunPatch,
    RunSelection,
    resolve_report_link,
)
from app.services import (
    add_cases_to_run,
    ensure_open,
    get_or_404,
    parse_case_ref,
    record_result,
    resolve_selection,
    run_stats,
    section_paths,
    tree_order,
)

router = APIRouter(prefix="/api", tags=["runs"])
Session = Annotated[AsyncSession, Depends(get_session)]


async def run_out(session: AsyncSession, run: TestRun) -> RunOut:
    stats = (await run_stats(session, [run.id]))[run.id]
    return RunOut.model_validate(run).model_copy(update={"stats": stats})


def _latest_results(run_ids: list[int] | None = None, case_id: int | None = None):  # type: ignore[no-untyped-def]
    """Subquery: latest result per (run, case) plus how many results there are."""
    ranked = select(
        TestResult,
        func.row_number()
        .over(
            partition_by=(TestResult.run_id, TestResult.case_id),
            order_by=(TestResult.created_at.desc(), TestResult.id.desc()),
        )
        .label("rn"),
        func.count().over(partition_by=(TestResult.run_id, TestResult.case_id)).label("n"),
    )
    if run_ids is not None:
        ranked = ranked.where(TestResult.run_id.in_(run_ids))
    if case_id is not None:
        ranked = ranked.where(TestResult.case_id == case_id)
    sub = ranked.subquery()
    return sub


def _result_out(result: TestResult, report_url: str | None) -> ResultOut:
    out = ResultOut.model_validate(result)
    return out.model_copy(update={"report_link": resolve_report_link(report_url, result.report_link)})


def _result_from_row(row, report_url: str | None) -> ResultOut | None:  # type: ignore[no-untyped-def]
    if row is None or getattr(row, "id", None) is None:
        return None
    return ResultOut(
        id=row.id,
        run_id=row.run_id,
        case_id=row.case_id,
        status=row.status,
        comment=row.comment,
        duration_ms=row.duration_ms,
        error_message=row.error_message,
        stack_trace=row.stack_trace,
        recorded_by=getattr(row, "recorded_by", None),
        report_link=resolve_report_link(report_url, row.report_link),
        created_at=row.created_at,
    )


# --- Runs ----------------------------------------------------------------------------


@router.get("/projects/{project_id}/runs", response_model=RunList)
async def list_runs(
    project_id: int,
    session: Session,
    closed: bool | None = None,
    source: RunSource | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: Literal["created_at", "name", "closed_at"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
) -> RunList:
    await get_or_404(session, Project, project_id)
    stmt = select(TestRun).where(TestRun.project_id == project_id)
    if closed is not None:
        stmt = stmt.where(TestRun.closed == closed)
    if source is not None:
        stmt = stmt.where(TestRun.source == source)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    runs = list(
        await session.scalars(
            stmt.order_by(*_run_order(sort, order)).limit(limit).offset(offset)
        )
    )
    stats = await run_stats(session, [r.id for r in runs])
    return RunList(
        items=[RunOut.model_validate(r).model_copy(update={"stats": stats[r.id]}) for r in runs],
        total=total or 0,
    )


def _run_order(sort: str, order: str) -> list:  # type: ignore[type-arg]
    key = {"created_at": TestRun.created_at, "name": func.lower(TestRun.name), "closed_at": TestRun.closed_at}[sort]
    desc = order == "desc"
    return [(key.desc() if desc else key.asc()).nulls_last(), TestRun.id.desc() if desc else TestRun.id.asc()]


@router.post("/projects/{project_id}/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
async def create_run(project_id: int, body: RunIn, session: Session, principal: CurrentPrincipal) -> RunOut:
    """Create a manual run. Cases come from `case_ids`, `suite_id`, `section_ids` and/or `filter`."""
    await get_or_404(session, Project, project_id)
    case_ids = await resolve_selection(session, project_id, body)
    run = TestRun(
        project_id=project_id,
        name=body.name,
        description=body.description,
        source=RunSource.manual,
        created_by_id=principal.user.id,
    )
    session.add(run)
    await session.flush()
    await add_cases_to_run(session, run.id, case_ids)
    await session.commit()
    await session.refresh(run, ["created_by"])
    return await run_out(session, run)


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: int, session: Session) -> RunOut:
    return await run_out(session, await get_or_404(session, TestRun, run_id))


@router.patch("/runs/{run_id}", response_model=RunOut)
async def update_run(run_id: int, body: RunPatch, session: Session) -> RunOut:
    run = await get_or_404(session, TestRun, run_id)
    if body.name is not None:
        run.name = body.name
    if body.description is not None:
        run.description = body.description
    if "report_url" in body.model_fields_set:
        run.report_url = body.report_url
    if body.closed is not None and body.closed != run.closed:
        run.closed = body.closed
        run.closed_at = datetime.now(UTC) if body.closed else None
    await session.commit()
    return await run_out(session, run)


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(run_id: int, session: Session) -> None:
    run = await get_or_404(session, TestRun, run_id)
    await session.delete(run)
    await session.commit()


# --- Run membership --------------------------------------------------------------------


@router.get("/runs/{run_id}/cases", response_model=list[RunCaseOut])
async def list_run_cases(
    run_id: int,
    session: Session,
    status_: Annotated[list[ResultStatus] | None, Query(alias="status")] = None,
) -> list[RunCaseOut]:
    """Cases in the run with their current status and latest result, in tree order."""
    run = await get_or_404(session, TestRun, run_id)
    latest = _latest_results(run_ids=[run_id])
    stmt = (
        select(RunCase.status.label("current"), TestCase, latest, User.name.label("recorded_by"))
        .join(TestCase, TestCase.id == RunCase.case_id)
        .outerjoin(latest, (latest.c.case_id == RunCase.case_id) & (latest.c.rn == 1))
        .outerjoin(User, User.id == latest.c.user_id)
        .where(RunCase.run_id == run_id)
    )
    if status_:
        stmt = stmt.where(RunCase.status.in_(status_))
    rows = (await session.execute(stmt)).all()

    suite_ids = {r.TestCase.suite_id for r in rows}
    sections = list(await session.scalars(select(Section).where(Section.suite_id.in_(suite_ids))))
    paths = section_paths(sections)
    order = {sid: i for i, sid in enumerate(tree_order(sections))}

    def order_key(r):  # type: ignore[no-untyped-def]
        c = r.TestCase
        return (c.suite_id, order.get(c.section_id, 0), c.position, c.id)

    return [
        RunCaseOut(
            case_id=r.TestCase.id,
            key=r.TestCase.key,
            title=r.TestCase.title,
            priority=r.TestCase.priority,
            automation_status=r.TestCase.automation_status,
            suite_id=r.TestCase.suite_id,
            section_id=r.TestCase.section_id,
            section_path=paths.get(r.TestCase.section_id, ""),
            status=r.current,
            result_count=r.n or 0,
            last_result=_result_from_row(r, run.report_url),
        )
        for r in sorted(rows, key=order_key)
    ]


@router.post("/runs/{run_id}/cases", response_model=RunOut)
async def add_run_cases(run_id: int, body: RunSelection, session: Session) -> RunOut:
    run = await get_or_404(session, TestRun, run_id)
    ensure_open(run)
    await add_cases_to_run(session, run.id, await resolve_selection(session, run.project_id, body))
    await session.commit()
    return await run_out(session, run)


@router.delete("/runs/{run_id}/cases/{case_ref}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_run_case(run_id: int, case_ref: str, session: Session) -> None:
    """Remove a case from the run (its results in this run are deleted too)."""
    run = await get_or_404(session, TestRun, run_id)
    ensure_open(run)
    case_id = parse_case_ref(case_ref)
    rc = await session.get(RunCase, (run_id, case_id))
    if rc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"C{case_id} is not in this run")
    await session.delete(rc)
    await session.execute(
        TestResult.__table__.delete().where(
            TestResult.run_id == run_id, TestResult.case_id == case_id
        )
    )
    await session.commit()


# --- Results ---------------------------------------------------------------------------


async def _check_members(session: AsyncSession, run_id: int, case_ids: set[int]) -> None:
    members = set(
        await session.scalars(
            select(RunCase.case_id).where(RunCase.run_id == run_id, RunCase.case_id.in_(case_ids))
        )
    )
    missing = sorted(case_ids - members)
    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Not in this run: {', '.join(f'C{i}' for i in missing)}",
        )


@router.post("/runs/{run_id}/results", response_model=ResultOut, status_code=status.HTTP_201_CREATED)
async def add_result(
    run_id: int, body: ResultIn, session: Session, principal: CurrentPrincipal
) -> ResultOut:
    """Record a result for a case in the run. It becomes the case's current status."""
    run = await get_or_404(session, TestRun, run_id)
    ensure_open(run)
    await _check_members(session, run_id, {body.case_id})
    result = await record_result(session, run_id, body, principal.user.id)
    await session.commit()
    await session.refresh(result, ["user"])
    return _result_out(result, run.report_url)


@router.post(
    "/runs/{run_id}/results/bulk", response_model=list[ResultOut], status_code=status.HTTP_201_CREATED
)
async def add_results_bulk(
    run_id: int, body: BulkResultsIn, session: Session, principal: CurrentPrincipal
) -> list[ResultOut]:
    run = await get_or_404(session, TestRun, run_id)
    ensure_open(run)
    await _check_members(session, run_id, {r.case_id for r in body.results})
    results = [await record_result(session, run_id, r, principal.user.id) for r in body.results]
    await session.commit()
    for r in results:
        await session.refresh(r, ["user"])
    return [_result_out(r, run.report_url) for r in results]


@router.get("/runs/{run_id}/cases/{case_ref}/results", response_model=list[ResultOut])
async def case_results_in_run(run_id: int, case_ref: str, session: Session) -> list[ResultOut]:
    """All results for one case in this run, newest first."""
    run = await get_or_404(session, TestRun, run_id)
    rows = await session.scalars(
        select(TestResult)
        .where(TestResult.run_id == run_id, TestResult.case_id == parse_case_ref(case_ref))
        .order_by(TestResult.created_at.desc(), TestResult.id.desc())
    )
    return [_result_out(r, run.report_url) for r in rows]


@router.get("/cases/{case_ref}/history", response_model=list[CaseHistoryItem])
async def case_history(
    case_ref: str, session: Session, limit: Annotated[int, Query(ge=1, le=500)] = 50
) -> list[CaseHistoryItem]:
    """Runs this case was part of, newest first, with its status in each."""
    case = await get_or_404(session, TestCase, parse_case_ref(case_ref))
    latest = _latest_results(case_id=case.id)
    rows = await session.execute(
        select(TestRun, RunCase.status.label("current"), latest, User.name.label("recorded_by"))
        .join(RunCase, (RunCase.run_id == TestRun.id) & (RunCase.case_id == case.id))
        .outerjoin(latest, (latest.c.run_id == TestRun.id) & (latest.c.rn == 1))
        .outerjoin(User, User.id == latest.c.user_id)
        .order_by(TestRun.created_at.desc(), TestRun.id.desc())
        .limit(limit)
    )
    return [
        CaseHistoryItem(
            run_id=r.TestRun.id,
            run_name=r.TestRun.name,
            run_source=r.TestRun.source,
            run_closed=r.TestRun.closed,
            run_created_at=r.TestRun.created_at,
            branch=r.TestRun.branch,
            status=r.current,
            result_count=r.n or 0,
            last_result=_result_from_row(r, r.TestRun.report_url),
        )
        for r in rows
    ]
