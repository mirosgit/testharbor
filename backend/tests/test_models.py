"""Model-level behavior: defaults, constraints, cascades, migrations in sync."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    AutomationStatus,
    Priority,
    Project,
    ResultStatus,
    RunCase,
    Section,
    Suite,
    TestCase,
    TestResult,
    TestRun,
)


async def _case_tree(session):  # type: ignore[no-untyped-def]
    p = Project(name="P")
    session.add(p)
    await session.flush()
    s = Suite(project_id=p.id, name="S")
    session.add(s)
    await session.flush()
    sec = Section(suite_id=s.id, name="Root")
    session.add(sec)
    await session.flush()
    return p, s, sec


async def test_case_defaults_and_key(session) -> None:  # type: ignore[no-untyped-def]
    p, s, sec = await _case_tree(session)
    c = TestCase(project_id=p.id, suite_id=s.id, section_id=sec.id, title="Login")
    session.add(c)
    await session.commit()
    assert c.key == f"C{c.id}"
    assert c.priority is Priority.medium
    assert c.automation_status is AutomationStatus.manual
    assert c.steps == [] and c.tags == []
    assert c.created_at is not None and c.updated_at is not None


async def test_automation_key_unique_per_project(session) -> None:  # type: ignore[no-untyped-def]
    p, s, sec = await _case_tree(session)
    for title in ("a", "b"):
        session.add(TestCase(project_id=p.id, suite_id=s.id, section_id=sec.id, title=title,
                             automation_key="tests/x.py::t"))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_null_automation_keys_do_not_conflict(session) -> None:  # type: ignore[no-untyped-def]
    p, s, sec = await _case_tree(session)
    for title in ("a", "b"):
        session.add(TestCase(project_id=p.id, suite_id=s.id, section_id=sec.id, title=title))
    await session.commit()


async def test_deleting_section_cascades_to_children_cases_and_results(session) -> None:  # type: ignore[no-untyped-def]
    p, s, sec = await _case_tree(session)
    child = Section(suite_id=s.id, parent_id=sec.id, name="Child")
    session.add(child)
    await session.flush()
    c = TestCase(project_id=p.id, suite_id=s.id, section_id=child.id, title="t")
    run = TestRun(project_id=p.id, name="R")
    session.add_all([c, run])
    await session.flush()
    session.add(RunCase(run_id=run.id, case_id=c.id, status=ResultStatus.passed))
    session.add(TestResult(run_id=run.id, case_id=c.id, status=ResultStatus.passed))
    await session.commit()

    await session.delete(sec)
    await session.commit()
    for model in (Section, TestCase, RunCase, TestResult):
        assert await session.scalar(select(func.count()).select_from(model)) == 0
    assert await session.scalar(select(func.count()).select_from(TestRun)) == 1


async def test_invalid_enum_rejected_by_db(session) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    p, s, sec = await _case_tree(session)
    await session.commit()
    with pytest.raises(IntegrityError):
        await session.execute(
            text("INSERT INTO test_cases (project_id, suite_id, section_id, title, priority) "
                 "VALUES (:p, :s, :sec, 'x', 'urgent')"),
            {"p": p.id, "s": s.id, "sec": sec.id},
        )


def test_migrations_match_models() -> None:
    """Fails if someone changes models without adding a migration."""
    import asyncio
    import concurrent.futures

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.config import get_settings
    from app.models import Base

    TEST_DB = get_settings().database_url

    async def diff() -> list:  # type: ignore[type-arg]
        eng = create_async_engine(TEST_DB)
        async with eng.connect() as conn:
            result = await conn.run_sync(
                lambda c: compare_metadata(MigrationContext.configure(c), Base.metadata)
            )
        await eng.dispose()
        return result

    with concurrent.futures.ThreadPoolExecutor() as ex:
        assert ex.submit(asyncio.run, diff()).result() == []
