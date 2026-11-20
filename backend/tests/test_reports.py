"""Runs' HTML reports: uploaded as a zip, served sandboxed by a signed link."""

import io
import zipfile
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.config import get_settings


@pytest.fixture(autouse=True)
def reports_dir(tmp_path: Path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(get_settings(), "reports_dir", str(tmp_path / "reports"))
    return tmp_path / "reports"


def make_zip(files: dict[str, bytes], symlink: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (0o120777 << 16)
            zf.writestr(info, "/etc/passwd")
    return buf.getvalue()


async def _upload(client: AsyncClient, run_id: int, data: bytes, page: str = "index.html"):  # type: ignore[no-untyped-def]
    return await client.put(f"/api/runs/{run_id}/report", params={"page": page},
                            files={"file": ("report.zip", data, "application/zip")})


async def test_upload_and_open_a_report(client: AsyncClient, make, reports_dir: Path) -> None:  # type: ignore[no-untyped-def]
    p, s, sec = await make.tree()
    case = await make.case(sec["id"], "Login")
    run = (await client.post(f"/api/projects/{p['id']}/runs", json={"name": "R", "case_ids": [case["id"]]})).json()
    junit = (f'<testsuites><testsuite name="x"><testcase name="t"><properties><property name="case_id" '
             f'value="{case["key"]}"/><property name="pw_test_id" value="abc123"/></properties>'
             f'<failure message="boom"/></testcase></testsuite></testsuites>').encode()
    await client.post(f"/api/projects/{p['id']}/runs/import-junit", params={"run_id": run["id"]},
                      files={"file": ("j.xml", junit, "application/xml")})

    r = await _upload(client, run["id"], make_zip({"index.html": b"<h1>report</h1>", "data/shot.png": b"png"}))
    assert r.status_code == 200, r.text
    url = r.json()["report_url"]
    assert url.startswith("/r/") and url.endswith("/index.html")
    # The result links to its test in the report.
    row = (await client.get(f"/api/runs/{run['id']}/cases")).json()[0]
    assert row["last_result"]["report_link"] == url + "#?testId=abc123"

    # Opened without any session (a fresh client), sandboxed.
    from httpx import ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as anon:
        page = await anon.get(url)
        assert page.status_code == 200 and page.text.endswith("<h1>report</h1>")
        assert page.text.startswith("<script>(function(){try{window.localStorage")  # storage shim first
        assert page.headers["content-security-policy"].startswith("sandbox allow-scripts")
        assert "allow-same-origin" not in page.headers["content-security-policy"]
        assert (await anon.get(url.replace("index.html", "data/shot.png"))).content == b"png"
        token = url.split("/")[2]
        assert (await anon.get(f"/r/{token}/../../etc/passwd")).status_code == 404
        assert (await anon.get(f"/r/{token}x/index.html")).status_code == 404  # a forged token
        assert (await anon.put(f"/api/runs/{run['id']}/report", files={"file": ("r.zip", b"x")})).status_code == 401

    # Deleting the run deletes its report.
    assert (reports_dir / str(run["id"])).is_dir()
    assert (await client.delete(f"/api/runs/{run['id']}")).status_code == 204
    assert not (reports_dir / str(run["id"])).exists()


async def test_unsafe_or_broken_reports_are_refused(client: AsyncClient, make, reports_dir: Path,  # type: ignore[no-untyped-def]
                                                    monkeypatch) -> None:
    p, s, sec = await make.tree()
    run = (await client.post(f"/api/projects/{p['id']}/runs", json={"name": "R"})).json()
    assert (await _upload(client, run["id"], b"not a zip")).status_code == 422
    assert (await _upload(client, run["id"], make_zip({"other.html": b"x"}))).status_code == 422  # no page
    assert (await _upload(client, run["id"], make_zip({"index.html": b"x"}), page="../x.html")).status_code == 422
    r = await _upload(client, run["id"], make_zip({"index.html": b"ok", "../../evil.txt": b"x", "/abs.txt": b"x"},
                                                   symlink="link"))
    assert r.status_code == 200
    stored = {str(f.relative_to(reports_dir)) for f in reports_dir.rglob("*") if f.is_file()}
    assert stored == {f"{run['id']}/index.html"}
    monkeypatch.setattr(get_settings(), "max_report_mb", 0)
    assert (await _upload(client, run["id"], make_zip({"index.html": b"x" * 10}))).status_code == 422
