import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.auth import current_principal
from app.config import get_settings
from app.routers import auth, automation, cases, io, jobs, projects, runs, sections, suites, users

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    if s.secret_key == "change-me-please":
        log.warning("SECRET_KEY is the default value - set it to a random string in production")
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models import User

    try:
        async with SessionLocal() as session:
            if not await session.scalar(select(func.count()).select_from(User)):
                log.warning(
                    "No users yet. Create the first admin with: "
                    "docker compose exec backend python -m app.manage create-admin"
                )
    except Exception:  # DB not migrated yet etc. - not fatal for startup
        pass
    yield


app = FastAPI(
    lifespan=lifespan,
    title="TestHarbor API",
    version="0.1.0",
    description=(
        "Self-hosted test case management.\n\n"
        "Authenticate with `Authorization: Bearer <token>` (create tokens in Settings › API tokens), "
        "or with the session cookie set by `POST /api/auth/login`. A token acts as the user who "
        "created it. Managing users and tokens requires a signed-in session.\n\n"
        "Case ids are accepted as `142` or `C142` wherever a case is referenced in a path."
    ),
)


@app.get("/api/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(users.router)  # mixes admin-only and public (accept invite) endpoints
protected = [Depends(current_principal)]
for module in (projects, suites, sections, cases, io, runs, automation, jobs):
    app.include_router(module.router, dependencies=protected)
