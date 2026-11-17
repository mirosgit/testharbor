from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Project, Suite, TestCase
from app.schemas import SuiteIn, SuiteOut, SuitePatch
from app.services import get_or_404

router = APIRouter(prefix="/api", tags=["suites"])
Session = Annotated[AsyncSession, Depends(get_session)]


async def _out(session: AsyncSession, suite: Suite) -> SuiteOut:
    count = await session.scalar(
        select(func.count()).select_from(TestCase).where(TestCase.suite_id == suite.id)
    )
    return SuiteOut.model_validate(suite).model_copy(update={"case_count": count or 0})


@router.get("/projects/{project_id}/suites", response_model=list[SuiteOut])
async def list_suites(project_id: int, session: Session) -> list[SuiteOut]:
    await get_or_404(session, Project, project_id)
    counts = (
        select(TestCase.suite_id, func.count().label("n")).group_by(TestCase.suite_id).subquery()
    )
    rows = await session.execute(
        select(Suite, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.suite_id == Suite.id)
        .where(Suite.project_id == project_id)
        .order_by(Suite.name, Suite.id)
    )
    return [SuiteOut.model_validate(s).model_copy(update={"case_count": n}) for s, n in rows]


@router.post(
    "/projects/{project_id}/suites", response_model=SuiteOut, status_code=status.HTTP_201_CREATED
)
async def create_suite(project_id: int, body: SuiteIn, session: Session) -> SuiteOut:
    await get_or_404(session, Project, project_id)
    suite = Suite(project_id=project_id, **body.model_dump())
    session.add(suite)
    await session.commit()
    return await _out(session, suite)


@router.get("/suites/{suite_id}", response_model=SuiteOut)
async def get_suite(suite_id: int, session: Session) -> SuiteOut:
    return await _out(session, await get_or_404(session, Suite, suite_id))


@router.patch("/suites/{suite_id}", response_model=SuiteOut)
async def update_suite(suite_id: int, body: SuitePatch, session: Session) -> SuiteOut:
    suite = await get_or_404(session, Suite, suite_id)
    for k, v in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(suite, k, v)
    await session.commit()
    return await _out(session, suite)


@router.delete("/suites/{suite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_suite(suite_id: int, session: Session) -> None:
    suite = await get_or_404(session, Suite, suite_id)
    await session.delete(suite)
    await session.commit()
