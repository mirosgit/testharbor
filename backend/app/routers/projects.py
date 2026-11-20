from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.db import get_session
from app.models import Project, Suite, TestCase, TestRun
from app.reports import delete_reports
from app.schemas import ProjectIn, ProjectOut, ProjectPatch, RoleRename, _clean_roles
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


@router.post("/{project_id}/roles/rename", response_model=ProjectOut)
async def rename_role(project_id: int, body: RoleRename, session: Session) -> ProjectOut:
    """Rename a role in the project's list and on every case that has it."""
    project = await get_or_404(session, Project, project_id)
    old, new = body.old.strip(), " ".join(body.new.split())
    if not new:
        raise HTTPException(422, "New name is empty")
    same = old.lower()
    if same not in {r.lower() for r in project.roles}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Role {old!r} is not in the project")

    def swap(roles: list[str]) -> list[str]:  # rename in place, merge if `new` already exists
        return _clean_roles([new if r.lower() == same else r for r in roles])

    project.roles = swap(project.roles)
    cases = await session.scalars(
        select(TestCase).where(TestCase.project_id == project_id, func.cardinality(TestCase.roles) > 0)
    )
    for case in cases:
        if any(r.lower() == same for r in case.roles):
            case.roles = swap(case.roles)
    await session.commit()
    return (await _with_counts(session, project_id))[0]


@router.delete(
    "/{project_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)]
)
async def delete_project(project_id: int, session: Session) -> None:
    project = await get_or_404(session, Project, project_id)
    run_ids = list(await session.scalars(select(TestRun.id).where(TestRun.project_id == project_id)))
    await session.delete(project)
    await session.commit()
    delete_reports(run_ids)
