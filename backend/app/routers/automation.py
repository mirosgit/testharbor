"""API tokens and JUnit XML import."""

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import generate_token, hash_token
from app.db import get_session
from app.junit import STATUS_SEVERITY, JUnitCase, JUnitParseError, parse_junit
from app.models import (
    ApiToken,
    AutomationStatus,
    Project,
    RunSource,
    Section,
    Suite,
    TestCase,
    TestRun,
)
from app.schemas import (
    JUnitImportResult,
    ResultIn,
    TokenCreated,
    TokenIn,
    TokenOut,
    UnmatchedTest,
)
from app.services import ensure_open, get_or_404, next_case_position, record_result

router = APIRouter(prefix="/api", tags=["automation"])
Session = Annotated[AsyncSession, Depends(get_session)]

UNSORTED_SUITE = "Unsorted"
AUTOMATED_SECTION = "Automated"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


# --- Tokens --------------------------------------------------------------------------


@router.get("/tokens", response_model=list[TokenOut])
async def list_tokens(session: Session) -> list[ApiToken]:
    return list(await session.scalars(select(ApiToken).order_by(ApiToken.created_at.desc())))


@router.post("/tokens", response_model=TokenCreated, status_code=status.HTTP_201_CREATED)
async def create_token(body: TokenIn, session: Session) -> TokenCreated:
    """Create an API token. The plain token is returned once and never stored."""
    token = generate_token()
    api_token = ApiToken(name=body.name, token_hash=hash_token(token), prefix=token[:10])
    session.add(api_token)
    await session.commit()
    return TokenCreated(**TokenOut.model_validate(api_token).model_dump(), token=token)


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(token_id: int, session: Session) -> None:
    api_token = await get_or_404(session, ApiToken, token_id)
    if api_token.revoked_at is None:
        api_token.revoked_at = datetime.now(UTC)
        await session.commit()


# --- JUnit import --------------------------------------------------------------------


async def _automated_section(session: AsyncSession, project_id: int) -> Section:
    """The "Unsorted" suite / "Automated" section for auto-created cases (created on demand)."""
    suite = await session.scalar(
        select(Suite).where(Suite.project_id == project_id, Suite.name == UNSORTED_SUITE).limit(1)
    )
    if suite is None:
        suite = Suite(project_id=project_id, name=UNSORTED_SUITE,
                      description="Cases created automatically from test results. Move them where they belong.")
        session.add(suite)
        await session.flush()
    section = await session.scalar(
        select(Section)
        .where(Section.suite_id == suite.id, Section.name == AUTOMATED_SECTION, Section.parent_id.is_(None))
        .limit(1)
    )
    if section is None:
        section = Section(suite_id=suite.id, name=AUTOMATED_SECTION)
        session.add(section)
        await session.flush()
    return section


@router.post("/projects/{project_id}/runs/import-junit", response_model=JUnitImportResult)
async def import_junit(
    project_id: int,
    file: list[UploadFile],
    session: Session,
    run_name: Annotated[str | None, Query(max_length=300)] = None,
    branch: Annotated[str | None, Query(max_length=300)] = None,
    commit: Annotated[str | None, Query(max_length=100)] = None,
    build_url: Annotated[str | None, Query(max_length=2000)] = None,
    description: str = "",
    auto_create: bool = False,
    run_id: Annotated[int | None, Query(description="Append to this open run instead of creating one")] = None,
) -> JUnitImportResult:
    """Upload one or more JUnit XML files (repeat the `file` field) as a CI test run.

    Each test is mapped to a case by, in order: a `case_id` property or `C123` in the test
    name; then `automation_key`; otherwise it is reported as unmatched, or, with
    `auto_create=true`, a new case is created in Unsorted › Automated.
    """
    await get_or_404(session, Project, project_id)

    tests: list[JUnitCase] = []
    for f in file:
        data = await f.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"{f.filename}: larger than 50 MB")
        try:
            tests += parse_junit(data)
        except JUnitParseError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{f.filename or 'file'}: {e}") from e

    # Run: append to an existing one, or create a new CI run.
    if run_id is not None:
        run = await get_or_404(session, TestRun, run_id)
        if run.project_id != project_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Run belongs to another project")
        ensure_open(run)
    else:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        run = TestRun(
            project_id=project_id,
            name=run_name or f"Automated run {now}",
            description=description,
            source=RunSource.ci,
            branch=branch or None,
            commit=commit or None,
            build_url=build_url or None,
        )
        session.add(run)
        await session.flush()

    # Look up everything we might match in two queries.
    wanted_ids = {i for t in tests for i in t.case_ids()}
    existing_ids = set(
        await session.scalars(
            select(TestCase.id).where(TestCase.project_id == project_id, TestCase.id.in_(wanted_ids))
        )
    ) if wanted_ids else set()
    wanted_keys = {k for t in tests for k in t.candidate_keys()}
    by_key: dict[str, int] = dict(
        (await session.execute(
            select(TestCase.automation_key, TestCase.id).where(
                TestCase.project_id == project_id, TestCase.automation_key.in_(wanted_keys)
            )
        )).tuples().all()
    ) if wanted_keys else {}

    pending: dict[int, list[JUnitCase]] = defaultdict(list)
    unmatched: list[UnmatchedTest] = []
    matched = created = 0
    section: Section | None = None
    position: int | None = None

    for t in tests:
        ids = t.case_ids()
        hit_ids = [i for i in ids if i in existing_ids]
        if hit_ids:
            matched += 1
            for i in hit_ids:
                pending[i].append(t)
            continue
        key_hit = next((by_key[k] for k in t.candidate_keys() if k in by_key), None)
        if key_hit is not None:
            matched += 1
            pending[key_hit].append(t)
            continue
        if auto_create:
            if section is None:
                section = await _automated_section(session, project_id)
                position = await next_case_position(session, section.id)
            assert position is not None
            case = TestCase(
                project_id=project_id,
                suite_id=section.suite_id,
                section_id=section.id,
                title=t.name[:500],
                automation_status=AutomationStatus.automated,
                automation_key=t.default_key()[:1000],
                position=position,
            )
            position += 1
            session.add(case)
            await session.flush()
            by_key[case.automation_key] = case.id  # type: ignore[index]
            created += 1
            pending[case.id].append(t)
            continue
        reason = (
            f"{', '.join(f'C{i}' for i in ids)} not found in this project" if ids
            else "no case with a matching case id or automation_key"
        )
        unmatched.append(UnmatchedTest(name=t.name, classname=t.classname, reason=reason))

    statuses: Counter[str] = Counter()
    for case_id, results in pending.items():
        # Worst status last, so it becomes the case's current status in the run.
        for t in sorted(results, key=lambda r: STATUS_SEVERITY[r.status]):
            await record_result(session, run.id, ResultIn(
                case_id=case_id,
                status=t.status,
                duration_ms=t.duration_ms(),
                error_message=t.message,
                stack_trace=t.details,
                comment=t.display_name if len(results) > 1 else None,
            ))
            statuses[t.status.value] += 1

    await session.commit()
    return JUnitImportResult(
        run_id=run.id,
        run_name=run.name,
        total=len(tests),
        matched=matched,
        created=created,
        unmatched=unmatched,
        statuses=dict(statuses),
    )
