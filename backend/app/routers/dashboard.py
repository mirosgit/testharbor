"""A project's dashboard: how much is automated, what waits for review, how tests are doing.

Everything is counted in the database in one request. "Live" cases are the ones that are not
Outdated or Rejected: coverage and the breakdowns count only those. Results are the ones recorded
in the chosen period (`days`), compared with the period just before it.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import (
    AutomationAgent,
    AutomationJob,
    AutomationProgress,
    AutomationStatus,
    CaseState,
    Priority,
    Project,
    ResultStatus,
    Section,
    Suite,
    TestCase,
    TestResult,
    TestRun,
)
from app.routers.jobs import AGENT_ONLINE
from app.schemas import (
    Dashboard,
    DashboardArea,
    DashboardAutomation,
    DashboardCaseRow,
    DashboardCoverage,
    DashboardDay,
    DashboardPriority,
    DashboardResults,
    DashboardReview,
    DashboardRun,
    DashboardSuite,
)
from app.services import get_or_404, run_stats

router = APIRouter(prefix="/api", tags=["dashboard"])
Session = Annotated[AsyncSession, Depends(get_session)]

LIVE = TestCase.state.notin_([CaseState.outdated, CaseState.rejected])
AUTOMATED = TestCase.automation_status == AutomationStatus.automated
EXECUTED = (ResultStatus.passed, ResultStatus.failed, ResultStatus.blocked, ResultStatus.retest)


def _n(cond):  # type: ignore[no-untyped-def]
    return func.count().filter(cond)


def _rate(passed: int, executed: int) -> float | None:
    return round(100 * passed / executed, 1) if executed else None


@router.get("/projects/{project_id}/dashboard", response_model=Dashboard)
async def dashboard(project_id: int, session: Session, days: Annotated[int, Query(ge=1, le=365)] = 30) -> Dashboard:
    await get_or_404(session, Project, project_id)
    now = datetime.now(UTC)
    since, before = now - timedelta(days=days), now - timedelta(days=2 * days)
    in_project = TestCase.project_id == project_id

    # --- Cases: states, automation, priorities -------------------------------------------
    by_state = {s.value: 0 for s in CaseState}
    for st, n in await session.execute(select(TestCase.state, func.count()).where(in_project).group_by(TestCase.state)):
        by_state[st.value] = n
    automation = {a.value: 0 for a in AutomationStatus}
    for st, n in await session.execute(
        select(TestCase.automation_status, func.count()).where(in_project, LIVE).group_by(TestCase.automation_status)
    ):
        automation[st.value] = n
    cannot = await session.scalar(
        select(func.count()).where(in_project, LIVE, ~AUTOMATED,
                                   TestCase.automation_progress == AutomationProgress.cannot_be_automated)
    ) or 0
    live = sum(automation.values())
    automated = automation[AutomationStatus.automated.value]
    coverage = DashboardCoverage(
        live=live, automated=automated, to_be_automated=automation[AutomationStatus.to_be_automated.value],
        manual=automation[AutomationStatus.manual.value], cannot_be_automated=cannot,
        percent=_rate(automated, live), automatable_percent=_rate(automated, live - cannot),
    )

    prio = {p.value: DashboardPriority(priority=p.value) for p in Priority}
    for p, total, auto in await session.execute(
        select(TestCase.priority, func.count(), _n(AUTOMATED)).where(in_project, LIVE).group_by(TestCase.priority)
    ):
        prio[p.value].total, prio[p.value].automated = total, auto

    # --- Suites and top-level sections ("areas") ------------------------------------------
    suites = {s.id: s for s in await session.scalars(select(Suite).where(Suite.project_id == project_id))}
    suite_rows = []
    for sid, total, auto, planned, review in await session.execute(
        select(TestCase.suite_id, _n(LIVE), _n(LIVE & AUTOMATED),
               _n(LIVE & (TestCase.automation_status == AutomationStatus.to_be_automated)),
               _n(TestCase.state == CaseState.pending_review))
        .where(in_project).group_by(TestCase.suite_id)
    ):
        suite_rows.append(DashboardSuite(id=sid, name=suites[sid].name, total=total, automated=auto,
                                         to_be_automated=planned, pending_review=review))
    suite_rows.sort(key=lambda s: (-s.total, s.name))

    sections = (await session.execute(
        select(Section.id, Section.parent_id, Section.name, Section.suite_id)
        .join(Suite, Suite.id == Section.suite_id).where(Suite.project_id == project_id)
    )).all()
    parent = {sid: pid for sid, pid, _, _ in sections}
    names = {sid: (name, suite_id) for sid, _, name, suite_id in sections}

    def root(sid: int) -> int:
        seen = set()
        while parent.get(sid) is not None and sid not in seen:
            seen.add(sid)
            sid = parent[sid]  # type: ignore[assignment]
        return sid

    areas: dict[int, DashboardArea] = {}
    for sec_id, total, auto in await session.execute(
        select(TestCase.section_id, func.count(), _n(AUTOMATED)).where(in_project, LIVE).group_by(TestCase.section_id)
    ):
        r = root(sec_id)
        name, suite_id = names.get(r, ("—", 0))
        a = areas.setdefault(r, DashboardArea(section_id=r, suite_id=suite_id, name=name,
                                              suite=suites[suite_id].name if suite_id in suites else ""))
        a.total += total
        a.automated += auto
    area_rows = sorted(areas.values(), key=lambda a: (-a.total, a.name))[:60]

    # --- Pending review -----------------------------------------------------------------
    review_q = select(func.count(), func.min(TestCase.updated_at)).where(in_project, TestCase.state == CaseState.pending_review)
    review_n, oldest = (await session.execute(review_q)).one()
    review = DashboardReview(count=review_n, oldest_at=oldest,
                             suite_id=max((s for s in suite_rows if s.pending_review), default=None,
                                          key=lambda s: s.pending_review).id if review_n else None)

    # --- Results in the period ------------------------------------------------------------
    project_results = (
        select(TestResult).join(TestRun, TestRun.id == TestResult.run_id).where(TestRun.project_id == project_id)
    ).subquery()
    day = cast(func.timezone("UTC", project_results.c.created_at), Date)
    per_day: dict[date, DashboardDay] = {}
    start = since.date()
    for i in range(days + 1):
        d = start + timedelta(days=i)
        if d <= now.date():
            per_day[d] = DashboardDay(date=d)
    for d, st, n in await session.execute(
        select(day, project_results.c.status, func.count())
        .where(project_results.c.created_at >= since).group_by(day, project_results.c.status)
    ):
        if d in per_day:
            setattr(per_day[d], st.value, n)
    days_rows = list(per_day.values())
    days_rows = days_rows[-days:]

    def period_counts(lo: datetime, hi: datetime):  # type: ignore[no-untyped-def]
        return select(
            _n(project_results.c.status == ResultStatus.passed),
            _n(project_results.c.status.in_(EXECUTED)),
            func.count(),
        ).where(project_results.c.created_at >= lo, project_results.c.created_at < hi)

    passed, executed, recorded = (await session.execute(period_counts(since, now + timedelta(seconds=1)))).one()
    p_passed, p_executed, _ = (await session.execute(period_counts(before, since))).one()
    tested_cases = await session.scalar(
        select(func.count(func.distinct(project_results.c.case_id))).where(project_results.c.created_at >= since)
    ) or 0
    results = DashboardResults(
        recorded=recorded, executed=executed, passed=passed, pass_rate=_rate(passed, executed),
        previous_pass_rate=_rate(p_passed, p_executed), tested_cases=tested_cases, days=days_rows,
    )

    # Failing most: the cases with the most failed results in the period.
    in_period = project_results.c.created_at >= since
    last_status = (
        select(TestResult.status).where(TestResult.case_id == project_results.c.case_id)
        .join(TestRun, TestRun.id == TestResult.run_id).where(TestRun.project_id == project_id)
        .order_by(TestResult.created_at.desc(), TestResult.id.desc()).limit(1).correlate(project_results)
        .scalar_subquery()
    )
    failing_q = (
        select(project_results.c.case_id, _n(project_results.c.status == ResultStatus.failed).label("fails"),
               func.count(), func.max(project_results.c.created_at), last_status)
        .where(in_period, project_results.c.status.in_(EXECUTED))
        .group_by(project_results.c.case_id)
        .having(_n(project_results.c.status == ResultStatus.failed) > 0)
        .order_by(_n(project_results.c.status == ResultStatus.failed).desc(), func.max(project_results.c.created_at).desc())
        .limit(8)
    )
    failing_rows = (await session.execute(failing_q)).all()

    # Flaky: passed and failed in turns. A flip is a result whose status differs from the one before.
    ordered = (
        select(project_results.c.case_id, project_results.c.status,
               func.lag(project_results.c.status).over(
                   partition_by=project_results.c.case_id,
                   order_by=(project_results.c.created_at, project_results.c.id)).label("prev"))
        .where(in_period, project_results.c.status.in_((ResultStatus.passed, ResultStatus.failed)))
    ).subquery()
    flaky_q = (
        select(ordered.c.case_id, _n(ordered.c.prev.isnot(None) & (ordered.c.status != ordered.c.prev)).label("flips"),
               func.count())
        .group_by(ordered.c.case_id)
        .having(_n(ordered.c.prev.isnot(None) & (ordered.c.status != ordered.c.prev)) >= 2)
        .order_by(_n(ordered.c.prev.isnot(None) & (ordered.c.status != ordered.c.prev)).desc(), ordered.c.case_id)
        .limit(8)
    )
    flaky_rows = (await session.execute(flaky_q)).all()

    ids = {r[0] for r in failing_rows} | {r[0] for r in flaky_rows}
    cases = {c.id: c for c in await session.scalars(select(TestCase).where(TestCase.id.in_(ids)))} if ids else {}

    def row(case_id: int, **kw) -> DashboardCaseRow | None:  # type: ignore[no-untyped-def]
        c = cases.get(case_id)
        return DashboardCaseRow(id=case_id, suite_id=c.suite_id, title=c.title,
                                automated=c.automation_status == AutomationStatus.automated, **kw) if c else None

    failing = [r for case_id, fails, total, last_at, last in failing_rows
               if (r := row(case_id, count=fails, results=total, last_at=last_at,
                            last_status=last.value if last else None))]
    flaky = [r for case_id, flips, total in flaky_rows if (r := row(case_id, count=flips, results=total))]

    # --- Runs -----------------------------------------------------------------------------
    runs = list(await session.scalars(
        select(TestRun).where(TestRun.project_id == project_id).order_by(TestRun.created_at.desc(), TestRun.id.desc()).limit(14)
    ))
    stats = await run_stats(session, [r.id for r in runs])
    run_rows = [
        DashboardRun(id=r.id, name=r.name, created_at=r.created_at, source=r.source.value, closed=r.closed,
                     **stats[r.id].model_dump())
        for r in reversed(runs)
    ]
    runs_in_period = await session.scalar(
        select(func.count()).where(TestRun.project_id == project_id, TestRun.created_at >= since)
    ) or 0

    # --- Autotests: agents and jobs ---------------------------------------------------------
    agents = list(await session.scalars(select(AutomationAgent).where(AutomationAgent.project_id == project_id)))
    jobs = {s: n for s, n in await session.execute(
        select(AutomationJob.status, func.count())
        .where(AutomationJob.project_id == project_id, AutomationJob.created_at >= since)
        .group_by(AutomationJob.status)
    )}
    last_job = await session.scalar(select(func.max(AutomationJob.created_at)).where(AutomationJob.project_id == project_id))
    autotests = DashboardAutomation(
        agents=len(agents), agents_online=sum(now - a.last_seen_at < AGENT_ONLINE for a in agents),
        jobs={s.value: n for s, n in jobs.items()}, last_job_at=last_job,
        catalog_managed=await session.scalar(select(func.count()).where(in_project, LIVE, TestCase.catalog_managed)) or 0,
    )

    return Dashboard(
        days=days, generated_at=now, cases_total=sum(by_state.values()), states=by_state, coverage=coverage,
        priorities=[prio[p.value] for p in (Priority.critical, Priority.high, Priority.medium, Priority.low)],
        suites=suite_rows, areas=area_rows, review=review, results=results, failing=failing, flaky=flaky,
        runs=run_rows, runs_in_period=runs_in_period, automation=autotests,
    )
