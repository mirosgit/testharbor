from fastapi import Depends, FastAPI

from app.auth import require_auth
from app.routers import auth, cases, io, projects, sections, suites

app = FastAPI(
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
for module in (projects, suites, sections, cases, io):
    app.include_router(module.router, dependencies=protected)
