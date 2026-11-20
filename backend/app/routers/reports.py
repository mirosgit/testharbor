"""Runs' HTML reports: agents upload them (`api`), browsers open them by a signed link (`public`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.db import get_session
from app.models import TestRun
from app.reports import (
    SANDBOX_CSP,
    ReportError,
    report_file,
    report_url,
    run_of_token,
    store_report,
    with_storage_shim,
)
from app.routers.runs import run_out
from app.schemas import RunOut
from app.services import get_or_404

api = APIRouter(prefix="/api", tags=["reports"])
public = APIRouter(tags=["reports"])
Session = Annotated[AsyncSession, Depends(get_session)]


@api.put("/runs/{run_id}/report", response_model=RunOut)
async def upload_report(
    run_id: int,
    file: UploadFile,
    session: Session,
    page: Annotated[str, Query(max_length=500, description="the report's start page inside the zip")] = "index.html",
) -> RunOut:
    """Store the run's HTML report (a zip of its folder); the run then links to it, and its results to their tests."""
    run = await get_or_404(session, TestRun, run_id)
    try:
        rel = await run_in_threadpool(store_report, run_id, file.file, page)
    except ReportError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    run.report_url = report_url(run_id, rel)
    await session.commit()
    await session.refresh(run)
    return await run_out(session, run)


@public.get("/r/{token}/{path:path}", include_in_schema=False)
async def open_report(token: str, path: str) -> Response:
    run_id = run_of_token(token)
    target = report_file(run_id, path or "index.html") if run_id is not None else None
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    headers = {
        "Content-Security-Policy": SANDBOX_CSP,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "private, max-age=3600",
    }
    if target.suffix.lower() in (".html", ".htm"):
        html = await run_in_threadpool(target.read_bytes)
        return Response(with_storage_shim(html), media_type="text/html; charset=utf-8", headers=headers)
    return FileResponse(target, headers=headers)
