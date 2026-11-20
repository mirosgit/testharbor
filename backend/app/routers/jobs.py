"""Run automated tests from TestHarbor.

A user starts a job (all tests, or selected cases); an agent (`testcli agent`) running on
the machine that has the tests claims it, runs its locally configured command, streams the
output here and uploads the report into the job's run. The server never sends commands:
only case ids, which the agent turns into a `--grep`, and values of the run options the agent
itself offers (its `--options` file), which it checks and passes on as environment variables.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.db import get_session
from app.models import (
    AutomationAgent,
    AutomationJob,
    JobStatus,
    Project,
    ResultStatus,
    RunCase,
    RunSource,
    TestCase,
    TestRun,
)
from app.schemas import AgentClaim, AgentOut, JobControl, JobDetail, JobFinish, JobIn, JobOut, JobProgress
from app.services import add_cases_to_run, ensure_open, get_or_404

router = APIRouter(prefix="/api", tags=["automation jobs"])
Session = Annotated[AsyncSession, Depends(get_session)]

MAX_LOG = 512 * 1024  # keep the tail of the output
AGENT_ONLINE = timedelta(seconds=30)  # agents poll every few seconds
STALE_JOB = timedelta(minutes=2)  # a running job whose agent stopped reporting
ACTIVE = (JobStatus.queued, JobStatus.running)


def _now() -> datetime:
    return datetime.now(UTC)


async def _expire_stale(session: AsyncSession, project_id: int) -> None:
    """Running jobs whose agent went silent are marked as errors."""
    await session.execute(
        update(AutomationJob)
        .where(
            AutomationJob.project_id == project_id,
            AutomationJob.status == JobStatus.running,
            AutomationJob.heartbeat_at < _now() - STALE_JOB,
        )
        .values(status=JobStatus.error, message="The agent stopped responding", finished_at=_now())
    )


async def _job(session: AsyncSession, job_id: int, lock: bool = False) -> AutomationJob:
    stmt = select(AutomationJob).where(AutomationJob.id == job_id)
    if lock:
        stmt = stmt.with_for_update(of=AutomationJob)
    job = await session.scalar(stmt)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job


def _append(job: AutomationJob, chunk: str) -> None:
    if chunk:
        job.log = (job.log + chunk)[-MAX_LOG:]


# --- People ----------------------------------------------------------------------------


@router.post("/projects/{project_id}/automation/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def start_job(project_id: int, body: JobIn, session: Session, principal: CurrentPrincipal) -> AutomationJob:
    """Queue a test run for an agent. Without `run_id` a new CI run is created."""
    await get_or_404(session, Project, project_id)
    case_ids = list(dict.fromkeys(body.case_ids))
    if case_ids:
        found = set(await session.scalars(
            select(TestCase.id).where(TestCase.project_id == project_id, TestCase.id.in_(case_ids))
        ))
        missing = [i for i in case_ids if i not in found]
        if missing:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Cases not found in this project: {', '.join(f'C{i}' for i in missing)}")

    if body.run_id is not None:
        run = await get_or_404(session, TestRun, body.run_id)
        if run.project_id != project_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Run belongs to another project")
        ensure_open(run)
        if body.only_failed:
            case_ids = list(await session.scalars(
                select(RunCase.case_id).where(RunCase.run_id == run.id, RunCase.status == ResultStatus.failed)
                .order_by(RunCase.case_id)
            ))
            if not case_ids:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "This run has no failed cases")
        busy = await session.scalar(
            select(AutomationJob.id).where(AutomationJob.run_id == run.id, AutomationJob.status.in_(ACTIVE))
        )
        if busy:
            raise HTTPException(status.HTTP_409_CONFLICT, "Autotests are already queued or running for this run")
    else:
        run = TestRun(
            project_id=project_id,
            name=(body.name or "").strip() or f"Autotests {_now().strftime('%Y-%m-%d %H:%M UTC')}",
            source=RunSource.ci,
            created_by_id=principal.user.id,
        )
        session.add(run)
        await session.flush()
    await add_cases_to_run(session, run.id, case_ids)

    job = AutomationJob(project_id=project_id, run_id=run.id, case_ids=case_ids, params=body.params,
                        requested_by_id=principal.user.id)
    session.add(job)
    await session.commit()
    await session.refresh(job, ["requested_by"])
    return job


@router.get("/projects/{project_id}/automation/jobs", response_model=list[JobOut])
async def list_jobs(
    project_id: int,
    session: Session,
    run_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[AutomationJob]:
    await _expire_stale(session, project_id)
    await session.commit()
    stmt = select(AutomationJob).where(AutomationJob.project_id == project_id)
    if run_id is not None:
        stmt = stmt.where(AutomationJob.run_id == run_id)
    return list(await session.scalars(stmt.order_by(AutomationJob.id.desc()).limit(limit)))


@router.get("/automation/jobs/{job_id}", response_model=JobDetail)
async def get_job(job_id: int, session: Session) -> AutomationJob:
    job = await _job(session, job_id)
    await _expire_stale(session, job.project_id)
    await session.commit()
    await session.refresh(job)
    return job


@router.post("/automation/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: int, session: Session) -> AutomationJob:
    """Stop a queued job, or ask the agent to stop a running one."""
    job = await _job(session, job_id, lock=True)
    if job.status in ACTIVE:
        job.status = JobStatus.cancelled
        job.finished_at = _now()
        await session.commit()
    return job


@router.get("/projects/{project_id}/automation/agents", response_model=list[AgentOut])
async def list_agents(project_id: int, session: Session) -> list[AgentOut]:
    rows = await session.scalars(
        select(AutomationAgent).where(AutomationAgent.project_id == project_id)
        .order_by(AutomationAgent.last_seen_at.desc())
    )
    now = _now()
    return [AgentOut(name=a.name, last_seen_at=a.last_seen_at, online=now - a.last_seen_at < AGENT_ONLINE,
                     options=a.options or [])
            for a in rows]


# --- Agents ----------------------------------------------------------------------------


@router.post("/projects/{project_id}/automation/claim", response_model=JobOut,
             responses={204: {"description": "Nothing to run"}})
async def claim_job(project_id: int, body: AgentClaim, session: Session, principal: CurrentPrincipal):  # type: ignore[no-untyped-def]
    """Agents poll this: takes the oldest queued job of the project, or returns 204."""
    await get_or_404(session, Project, project_id)
    name = " ".join(body.agent.split())
    options = [o.model_dump(exclude_none=True) for o in body.options]
    await session.execute(
        pg_insert(AutomationAgent)
        .values(project_id=project_id, name=name, user_id=principal.user.id, last_seen_at=_now(), options=options)
        .on_conflict_do_update(
            constraint="uq_automation_agents_project_name",
            set_={"last_seen_at": _now(), "user_id": principal.user.id, "options": options},
        )
    )
    await _expire_stale(session, project_id)
    job = await session.scalar(
        select(AutomationJob)
        .where(AutomationJob.project_id == project_id, AutomationJob.status == JobStatus.queued)
        .order_by(AutomationJob.id)
        .limit(1)
        .with_for_update(skip_locked=True, of=AutomationJob)
    )
    if job is None:
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    job.status = JobStatus.running
    job.agent = name
    job.started_at = job.heartbeat_at = _now()
    await session.commit()
    await session.refresh(job, ["requested_by"])
    keys = list(await session.scalars(
        select(TestCase.automation_key)
        .where(TestCase.id.in_(job.case_ids), TestCase.automation_key.is_not(None))
        .order_by(TestCase.id)
    )) if job.case_ids else []
    return JobOut.model_validate(job).model_copy(update={"automation_keys": keys})


@router.post("/automation/jobs/{job_id}/progress", response_model=JobControl)
async def job_progress(job_id: int, body: JobProgress, session: Session) -> JobControl:
    """New output from the agent; the answer tells it whether to stop."""
    job = await _job(session, job_id, lock=True)
    if job.status != JobStatus.running:
        return JobControl(cancelled=True)
    _append(job, body.log)
    job.heartbeat_at = _now()
    await session.commit()
    return JobControl(cancelled=False)


@router.post("/automation/jobs/{job_id}/finish", response_model=JobOut)
async def finish_job(job_id: int, body: JobFinish, session: Session) -> AutomationJob:
    job = await _job(session, job_id, lock=True)
    _append(job, body.log)
    if job.status == JobStatus.running:
        job.status = JobStatus(body.status)
        job.exit_code = body.exit_code
        job.message = body.message
        job.finished_at = _now()
    await session.commit()
    await session.refresh(job, ["requested_by"])
    return job
