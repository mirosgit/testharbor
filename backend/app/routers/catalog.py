"""The automated tests' catalog: agents upload it, people preview and sync it into cases (app/catalog.py)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.catalog import AUTOTESTS_SUITE, PlanItem, SyncError, apply_sync, plan_sync
from app.db import get_session
from app.models import AutomationCatalog, Project
from app.schemas import (
    CatalogApplied,
    CatalogApply,
    CatalogIn,
    CatalogItemOut,
    CatalogPreview,
    CatalogSuggestionOut,
    CatalogTest,
)
from app.services import get_or_404

router = APIRouter(prefix="/api", tags=["automation catalog"])
Session = Annotated[AsyncSession, Depends(get_session)]

ACTION_ORDER = {"create": 0, "link": 1, "update": 2, "outdated": 3, "unchanged": 4}


def _item(i: PlanItem) -> CatalogItemOut:
    return CatalogItemOut(
        action=i.action, key=i.key, title=i.title, path=i.path,
        case_id=i.case.id if i.case else None,
        case_key=f"C{i.case.id}" if i.case else None,
        case_title=i.case.title if i.case else None,
        changes=i.changes, note=i.note,
        suggestions=[CatalogSuggestionOut(case_id=s.case_id, key=f"C{s.case_id}", title=s.title, path=s.path,
                                          score=s.score) for s in i.suggestions],
    )


async def _catalog(session: AsyncSession, project_id: int) -> AutomationCatalog:
    await get_or_404(session, Project, project_id)
    catalog = await session.scalar(select(AutomationCatalog).where(AutomationCatalog.project_id == project_id))
    if catalog is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "No catalog yet: start `testcli agent` with --catalog for this project")
    return catalog


async def _preview(session: AsyncSession, catalog: AutomationCatalog) -> CatalogPreview:
    tests = [CatalogTest.model_validate(t) for t in catalog.tests]
    items = await plan_sync(session, catalog.project_id, tests)
    counts = {a: 0 for a in ACTION_ORDER}
    for i in items:
        counts[i.action] += 1
    items.sort(key=lambda i: (ACTION_ORDER[i.action], i.path, i.title))
    return CatalogPreview(agent=catalog.agent, uploaded_at=catalog.uploaded_at, suite=AUTOTESTS_SUITE,
                          counts=counts, items=[_item(i) for i in items])


@router.put("/projects/{project_id}/automation/catalog", response_model=CatalogPreview)
async def upload_catalog(project_id: int, body: CatalogIn, session: Session) -> CatalogPreview:
    """Agents: replace the project's catalog of automated tests. Changes nothing else; the answer is the preview."""
    await get_or_404(session, Project, project_id)
    tests = [t.model_dump() for t in body.tests]
    now = datetime.now(UTC)
    await session.execute(
        pg_insert(AutomationCatalog)
        .values(project_id=project_id, agent=body.agent, uploaded_at=now, tests=tests)
        .on_conflict_do_update(index_elements=[AutomationCatalog.project_id],
                               set_={"agent": body.agent, "uploaded_at": now, "tests": tests})
    )
    await session.commit()
    return await _preview(session, await _catalog(session, project_id))


@router.get("/projects/{project_id}/automation/catalog", response_model=CatalogPreview)
async def preview_catalog(project_id: int, session: Session) -> CatalogPreview:
    """What a sync would do: new tests (with similar existing cases), updates, links, outdated cases."""
    return await _preview(session, await _catalog(session, project_id))


@router.post("/projects/{project_id}/automation/catalog/apply", response_model=CatalogApplied)
async def apply_catalog(project_id: int, body: CatalogApply, session: Session,
                        principal: CurrentPrincipal) -> CatalogApplied:
    catalog = await _catalog(session, project_id)
    if catalog.uploaded_at != body.uploaded_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "The catalog changed since the preview; review it again")
    tests = [CatalogTest.model_validate(t) for t in catalog.tests]
    try:
        counts = await apply_sync(session, project_id, tests, links=body.links, skip=set(body.skip),
                                  user_name=principal.user.name)
    except SyncError as e:
        await session.rollback()
        raise HTTPException(422, str(e)) from e
    await session.commit()
    return CatalogApplied(**counts)
