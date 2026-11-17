from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Section, Suite, TestCase
from app.schemas import SectionIn, SectionOut, SectionPatch
from app.services import descendant_ids, get_or_404, suite_sections

router = APIRouter(prefix="/api", tags=["sections"])
Session = Annotated[AsyncSession, Depends(get_session)]


async def _counts(session: AsyncSession, section_ids: list[int]) -> dict[int, int]:
    if not section_ids:
        return {}
    rows = await session.execute(
        select(TestCase.section_id, func.count())
        .where(TestCase.section_id.in_(section_ids))
        .group_by(TestCase.section_id)
    )
    return dict(rows.tuples().all())


async def _out(session: AsyncSession, section: Section) -> SectionOut:
    n = (await _counts(session, [section.id])).get(section.id, 0)
    return SectionOut.model_validate(section).model_copy(update={"case_count": n})


def _reorder(siblings: list[Section], moving: Section, position: int | None) -> None:
    """Insert `moving` among `siblings` at `position` (None = end) and renumber."""
    ordered = [s for s in sorted(siblings, key=lambda s: (s.position, s.id)) if s.id != moving.id]
    idx = len(ordered) if position is None else max(0, min(position, len(ordered)))
    ordered.insert(idx, moving)
    for i, s in enumerate(ordered):
        s.position = i


@router.get("/suites/{suite_id}/sections", response_model=list[SectionOut])
async def list_sections(suite_id: int, session: Session) -> list[SectionOut]:
    """Flat list of all sections in the suite; build the tree with `parent_id` + `position`."""
    await get_or_404(session, Suite, suite_id)
    sections = await suite_sections(session, suite_id)
    counts = await _counts(session, [s.id for s in sections])
    return [
        SectionOut.model_validate(s).model_copy(update={"case_count": counts.get(s.id, 0)})
        for s in sections
    ]


@router.post(
    "/suites/{suite_id}/sections", response_model=SectionOut, status_code=status.HTTP_201_CREATED
)
async def create_section(suite_id: int, body: SectionIn, session: Session) -> SectionOut:
    await get_or_404(session, Suite, suite_id)
    if body.parent_id is not None:
        parent = await get_or_404(session, Section, body.parent_id)
        if parent.suite_id != suite_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Parent section belongs to another suite")
    last = await session.scalar(
        select(func.max(Section.position)).where(
            Section.suite_id == suite_id,
            Section.parent_id.is_(None) if body.parent_id is None else Section.parent_id == body.parent_id,
        )
    )
    section = Section(suite_id=suite_id, position=0 if last is None else last + 1, **body.model_dump())
    session.add(section)
    await session.commit()
    return await _out(session, section)


@router.get("/sections/{section_id}", response_model=SectionOut)
async def get_section(section_id: int, session: Session) -> SectionOut:
    return await _out(session, await get_or_404(session, Section, section_id))


@router.patch("/sections/{section_id}", response_model=SectionOut)
async def update_section(section_id: int, body: SectionPatch, session: Session) -> SectionOut:
    section = await get_or_404(session, Section, section_id)
    if body.name is not None:
        section.name = body.name
    if body.description is not None:
        section.description = body.description

    moving_parent = "parent_id" in body.model_fields_set
    if moving_parent or body.position is not None:
        sections = await suite_sections(session, section.suite_id)
        new_parent = body.parent_id if moving_parent else section.parent_id
        if new_parent is not None:
            if new_parent in descendant_ids(sections, section.id):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "Cannot move a section into itself or its descendant"
                )
            if not any(s.id == new_parent for s in sections):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Parent section not found in this suite")
        section.parent_id = new_parent
        siblings = [s for s in sections if s.parent_id == new_parent]
        _reorder(siblings, section, body.position)

    await session.commit()
    return await _out(session, section)


@router.delete("/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_section(section_id: int, session: Session) -> None:
    """Deletes the section, its subsections and all their cases."""
    section = await get_or_404(session, Section, section_id)
    await session.delete(section)
    await session.commit()
