"""HTML reports of runs (e.g. Playwright's), uploaded by agents and served by TestHarbor.

An agent uploads the report's folder as a zip (`PUT /api/runs/{id}/report`); it is unpacked into
`REPORTS_DIR/<run id>/` and the run's report URL becomes `/r/<token>/<page>`. The token is the run id
signed with SECRET_KEY: it can't be guessed, and every file of the report is reached under it, so
the report's own relative links (screenshots, traces) work without the session cookie.

A report is HTML and JavaScript made by the tests, so it is served sandboxed (CSP `sandbox` without
`allow-same-origin`): it runs in an opaque origin and can't read TestHarbor's cookies, storage or
API. Trace viewers that need a service worker don't work there; traces can still be downloaded.
"""

from __future__ import annotations

import shutil
import stat
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import IO

from itsdangerous import BadSignature, URLSafeSerializer

from app.config import get_settings

MAX_FILES = 20_000
SANDBOX_CSP = (
    "sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox allow-downloads allow-modals; "
    "frame-ancestors 'self'"
)


# A sandboxed page has no storage: reading localStorage throws, and report apps (Playwright's) stop. This
# goes first into every served HTML page: in-memory localStorage / sessionStorage when the real ones throw.
STORAGE_SHIM = (
    "<script>(function(){try{window.localStorage;return}catch(e){}"
    "function m(){var d=Object.create(null);return{getItem:function(k){return k in d?d[k]:null},"
    "setItem:function(k,v){d[k]=String(v)},removeItem:function(k){delete d[k]},"
    "clear:function(){for(var k in d)delete d[k]},key:function(i){return Object.keys(d)[i]||null},"
    "get length(){return Object.keys(d).length}}}"
    "try{Object.defineProperty(window,'localStorage',{value:m(),configurable:true});"
    "Object.defineProperty(window,'sessionStorage',{value:m(),configurable:true})}catch(e){}})();</script>"
)


def with_storage_shim(html: bytes) -> bytes:
    """The page with STORAGE_SHIM before anything else runs (after <head>, else at the very start)."""
    shim = STORAGE_SHIM.encode()
    lower = html[:4096].lower()
    at = lower.find(b"<head")
    if at != -1 and (end := html.find(b">", at)) != -1:
        return html[: end + 1] + shim + html[end + 1 :]
    return shim + html


class ReportError(ValueError):
    pass


def reports_dir() -> Path:
    return Path(get_settings().reports_dir)


def _signer() -> URLSafeSerializer:
    return URLSafeSerializer(get_settings().secret_key, salt="th-report")


def report_token(run_id: int) -> str:
    return str(_signer().dumps(run_id))


def run_of_token(token: str) -> int | None:
    try:
        value = _signer().loads(token)
    except BadSignature:
        return None
    return value if isinstance(value, int) else None


def report_url(run_id: int, page: str) -> str:
    return f"/r/{report_token(run_id)}/{page}"


def safe_member(name: str) -> PurePosixPath | None:
    """A zip member as a relative path inside the report, or None (directories, unsafe names)."""
    path = PurePosixPath(name.replace("\\", "/"))
    if name.endswith("/") or path.is_absolute() or ".." in path.parts or not path.parts or ":" in path.parts[0]:
        return None
    return path


def store_report(run_id: int, archive: IO[bytes], page: str) -> str:
    """Unpack a report zip for a run (replacing an earlier one); returns the page's path inside it."""
    limit = get_settings().max_report_mb * 1024 * 1024
    page_path = safe_member(page)
    if page_path is None:
        raise ReportError(f"Invalid report page {page!r}")
    try:
        zf = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as e:
        raise ReportError("The report must be a zip file") from e
    with zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        if len(members) > MAX_FILES:
            raise ReportError(f"Too many files in the report (more than {MAX_FILES})")
        if sum(m.file_size for m in members) > limit:
            raise ReportError(f"The report is larger than {get_settings().max_report_mb} MB unpacked")
        names = {str(p) for m in members if (p := safe_member(m.filename))}
        if str(page_path) not in names:
            raise ReportError(f"The report has no {page_path}")
        root = reports_dir()
        root.mkdir(parents=True, exist_ok=True)
        tmp = root / f".upload-{run_id}-{uuid.uuid4().hex}"
        try:
            written = 0
            for m in members:
                rel = safe_member(m.filename)
                if rel is None or stat.S_ISLNK(m.external_attr >> 16):
                    continue  # no symlinks, nothing outside the folder
                dest = tmp.joinpath(*rel.parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(m) as src, open(dest, "wb") as out:
                    while chunk := src.read(1024 * 1024):
                        written += len(chunk)
                        if written > limit:  # sizes in the zip's directory can lie
                            raise ReportError(f"The report is larger than {get_settings().max_report_mb} MB unpacked")
                        out.write(chunk)
            final = root / str(run_id)
            shutil.rmtree(final, ignore_errors=True)
            tmp.rename(final)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return str(page_path)


def report_file(run_id: int, path: str) -> Path | None:
    """A file of a run's report, or None if it doesn't exist or is outside the report."""
    base = (reports_dir() / str(run_id)).resolve()
    rel = safe_member(path)
    if rel is None:
        return None
    target = base.joinpath(*rel.parts).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        return None
    return target


def delete_reports(run_ids: list[int]) -> None:
    for run_id in run_ids:
        shutil.rmtree(reports_dir() / str(int(run_id)), ignore_errors=True)
