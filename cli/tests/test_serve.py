"""The agent serves the HTML reports and links runs to them."""

import json
import sys
import textwrap
import urllib.request
from pathlib import Path

import pytest

from test_agent import _Server, server  # noqa: F401  (fixture; tests/ is on sys.path)
from testharbor_cli import serve
from testharbor_cli.main import CliError, main


def test_split_report_path() -> None:
    assert serve.split_report_path("reports/t{job_id}/index.html") == ("reports", "t{job_id}/index.html")
    for bad in ("/abs/index.html", "../x/index.html", "index.html", "reports/../../etc/passwd"):
        with pytest.raises(CliError):
            serve.split_report_path(bad)


def test_serves_only_its_folder(tmp_path: Path) -> None:
    (tmp_path / "reports" / "t1").mkdir(parents=True)
    (tmp_path / "reports" / "t1" / "index.html").write_text("<h1>report</h1>")
    (tmp_path / ".env").write_text("SECRET=1")
    port = serve.start(tmp_path / "reports", 0)
    assert urllib.request.urlopen(f"http://127.0.0.1:{port}/t1/index.html").read() == b"<h1>report</h1>"
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(f"http://127.0.0.1:{port}/../.env")


def test_keep_report_copies_the_folder_and_prunes(tmp_path: Path) -> None:
    page = tmp_path / "co" / "reports" / "t5" / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text("x")
    (page.parent / "trace").mkdir()
    (page.parent / "trace" / "a.zip").write_text("z")
    store = tmp_path / "store"
    store.mkdir()
    for i in range(3):
        serve.keep_report(page, store, f"job-{i}", keep=2)
    assert sorted(p.name for p in store.iterdir()) == ["job-1", "job-2"]
    assert (store / "job-2" / "trace" / "a.zip").read_text() == "z"


def test_local_agent_links_the_run_to_its_report(server: str, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    (tmp_path / "run.py").write_text(textwrap.dedent("""\
        import os, pathlib
        d = pathlib.Path("reports") / ("t" + os.environ["TESTHARBOR_JOB_ID"])
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text("<p>report</p>")
        (d / "junit.xml").write_text('<testsuites><testsuite name="x"><testcase name="t">'
            '<properties><property name="pw_test_id" value="abc"/></properties></testcase></testsuite></testsuites>')
    """))
    (tmp_path / "testharbor.json").write_text(json.dumps({
        "url": server, "project": 3, "name": "box", "command": f"{sys.executable} run.py",
        "report": "reports/t{job_id}/junit.xml", "report_html": "reports/t{job_id}/index.html", "report_port": 0,
    }))
    monkeypatch.setenv("TESTHARBOR_TOKEN", "th_x")
    _Server.jobs = [{"id": 61, "run_id": 2, "case_ids": []}]
    assert main(["agent", "--cwd", str(tmp_path), "--once", "--poll", "0.05"]) == 0
    upload = next(p for p, _ in _Server.calls if "/runs/import-junit" in p)
    from urllib.parse import parse_qs, urlparse
    url = parse_qs(urlparse(upload).query)["report_url"][0]
    assert url.startswith("http://localhost:") and url.endswith("/t61/index.html")
    assert urllib.request.urlopen(url.replace("localhost", "127.0.0.1")).read() == b"<p>report</p>"
