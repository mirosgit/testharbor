from fastapi import FastAPI

app = FastAPI(
    title="TestHarbor API",
    version="0.1.0",
    description="Self-hosted test case management. Authenticate with `Authorization: Bearer <token>`.",
)


@app.get("/api/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
