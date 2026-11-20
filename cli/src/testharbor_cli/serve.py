"""A small static web server for the HTML reports of the runs, so TestHarbor can link to them.

Playwright's HTML report (and its Trace Viewer) needs to be served over HTTP, not opened as a file.
The agent serves one folder (e.g. `reports/`, never the whole project) on a local port; the run's
report link points there, and every result links to its test (`index.html#?testId=…`).
"""

from __future__ import annotations

import functools
import os
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath

from .main import CliError

DEFAULT_PORT = 9323


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args: object) -> None:  # one line per request would drown the agent's output
        pass


def start(folder: Path, port: int = DEFAULT_PORT, host: str = "127.0.0.1") -> int:
    """Serve `folder` in a background thread; returns the port (another free one if `port` is taken)."""
    folder.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(_Quiet, directory=str(folder))
    for candidate in (port, 0):
        try:
            server = ThreadingHTTPServer((host, candidate), handler)
        except OSError:
            continue
        threading.Thread(target=server.serve_forever, daemon=True, name="testharbor-reports").start()
        return int(server.server_address[1])
    raise CliError(f"cannot serve the reports on port {port}")


def split_report_path(report_html: str) -> tuple[str, str]:
    """`reports/t{job_id}/index.html` -> ("reports", "t{job_id}/index.html"): the folder that is served and
    the page inside it. Only a relative path inside the tests' folder is accepted."""
    path = PurePosixPath(report_html.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or len(path.parts) < 2:
        raise CliError(f"report_html {report_html!r}: a relative path like reports/index.html, inside the tests' "
                       "folder (the first folder is what gets served)")
    return path.parts[0], str(PurePosixPath(*path.parts[1:]))


def keep_report(page: Path, store: Path, name: str, keep: int = 50) -> None:
    """Copy the folder of a report page to `store/name` (a server checkout is removed after the run); only the
    latest `keep` reports are kept."""
    if not page.is_file():
        return
    dest = store / name
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(page.parent, dest, symlinks=False, ignore_dangling_symlinks=True)
    os.utime(dest)  # copytree keeps the source's time; the newest copy must sort first
    reports = sorted((p for p in store.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    for old in reports[keep:]:
        shutil.rmtree(old, ignore_errors=True)
