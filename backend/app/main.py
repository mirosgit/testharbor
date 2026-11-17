import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.auth import require_auth
from app.config import get_settings
from app.routers import auth, automation, cases, io, projects, runs, sections, suites

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    if s.secret_key == "change-me-please":
        log.warning("SECRET_KEY is the default value - set it to a random string in production")
    if s.admin_password == "admin":
        log.warning("ADMIN_PASSWORD is the default 'admin' - change it before exposing TestHarbor")
    yield


app = FastAPI(
    lifespan=lifespan,
    title="TestHarbor API",
    version="0.1.0",
    description=(
        "Self-hosted test case management.\n\n"
        "Authenticate with `Authorization: Bearer <token>` (create tokens in Settings), "
        "or with the session cookie set by `POST /api/auth/login`.\n\n"
        "Case ids are accepted as `142` or `C142` wherever a case is referenced in a path."
    ),
)


@app.get("/api/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)
protected = [Depends(require_auth)]
for module in (projects, suites, sections, cases, io, runs, automation):
    app.include_router(module.router, dependencies=protected)
