"""Test setup: a dedicated Postgres database, migrated with Alembic, truncated between tests.

Set TEST_DATABASE_URL to point elsewhere (docker compose sets it for the backend container).
"""

import os

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://testharbor:testharbor@localhost:5433/testharbor_test"
)
# Must happen before the app (and its engine) is imported.
os.environ["DATABASE_URL"] = TEST_DB
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "secret")
os.environ["SEED_DEMO"] = "false"

from collections.abc import AsyncIterator  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def migrated_db() -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["database_url"] = TEST_DB
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def session() -> AsyncIterator[Any]:
    async with SessionLocal() as s:
        yield s


@pytest.fixture
async def anon() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def client(anon: AsyncClient) -> AsyncClient:
    s = get_settings()
    r = await anon.post(
        "/api/auth/login", json={"username": s.admin_username, "password": s.admin_password}
    )
    assert r.status_code == 200, r.text
    return anon


# --- Small factories -----------------------------------------------------------------


class Factory:
    def __init__(self, client: AsyncClient) -> None:
        self.c = client

    async def _post(self, url: str, **body: Any) -> dict[str, Any]:
        r = await self.c.post(url, json=body)
        assert r.status_code == 201, r.text
        return r.json()

    async def project(self, name: str = "P", **kw: Any) -> dict[str, Any]:
        return await self._post("/api/projects", name=name, **kw)

    async def suite(self, project_id: int, name: str = "S", **kw: Any) -> dict[str, Any]:
        return await self._post(f"/api/projects/{project_id}/suites", name=name, **kw)

    async def section(self, suite_id: int, name: str = "Sec", **kw: Any) -> dict[str, Any]:
        return await self._post(f"/api/suites/{suite_id}/sections", name=name, **kw)

    async def case(self, section_id: int, title: str = "Case", **kw: Any) -> dict[str, Any]:
        return await self._post("/api/cases", section_id=section_id, title=title, **kw)

    async def tree(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        p = await self.project()
        s = await self.suite(p["id"])
        sec = await self.section(s["id"])
        return p, s, sec


@pytest.fixture
def make(client: AsyncClient) -> Factory:
    return Factory(client)
