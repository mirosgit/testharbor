from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.db import get_session
from app.models import Project, Suite, TestCase, TestRun
from app.schemas import ProjectIn, ProjectOut, ProjectPatch
from app.services import get_or_404

router = APIRouter(prefix="/api/projects", tags=["projects"])
Session = Annotated[AsyncSession, Depends(get_session)]


def _count(model, project_id_col):  # type: ignore[no-untyped-def]
    return (
        select(func.count())
        .select_from(model)
        .where(project_id_col == Project.id)
        .correlate(Project)
        .scalar_subquery()
    )


async def _with_counts(session: AsyncSession, project_id: int | None = None) -> list[ProjectOut]:
    stmt = select(
        Project,
        _count(Suite, Suite.project_id).label("suite_count"),
        _count(TestCase, TestCase.project_id).label("case_count"),
        _count(TestRun, TestRun.project_id).label("run_count"),
    ).order_by(Project.name, Project.id)
    if project_id is not None:
        stmt = stmt.where(Project.id == project_id)
    rows = await session.execute(stmt)
    return [
        ProjectOut.model_validate(p).model_copy(
            update={"suite_count": sc, "case_count": cc, "run_count": rc}
        )
        for p, sc, cc, rc in rows
    ]


@router.get("", response_model=list[ProjectOut])
async def list_projects(session: Session) -> list[ProjectOut]:
    return await _with_counts(session)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectIn, session: Session) -> ProjectOut:
    project = Project(**body.model_dump())
    session.add(project)
    await session.commit()
    return (await _with_counts(session, project.id))[0]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, session: Session) -> ProjectOut:
    await get_or_404(session, Project, project_id)
    return (await _with_counts(session, project_id))[0]


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: int, body: ProjectPatch, session: Session) -> ProjectOut:
    project = await get_or_404(session, Project, project_id)
    for k, v in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(project, k, v)
    await session.commit()
    return (await _with_counts(session, project_id))[0]


@router.delete(
    "/{project_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)]
)
async def delete_project(project_id: int, session: Session) -> None:
    project = await get_or_404(session, Project, project_id)
    await session.delete(project)
    await session.commit()
