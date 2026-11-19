"""testcli agent against a fake TestHarbor."""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from testharbor_cli import agent as agent_mod
from testharbor_cli.agent import AgentConfig, build_command, case_grep, run_agent

agent_mod.PROGRESS_EVERY = 0.2

# A stand-in for `npx playwright test`: prints, records its argv, writes a report.
FAKE_TESTS = r'''
import json, sys, pathlib, os
print("Running 2 tests", flush=True)
pathlib.Path("argv.json").write_text(json.dumps({"argv": sys.argv[1:], "run": os.environ["TESTHARBOR_RUN_ID"]}))
if "--no-report" not in sys.argv:
    pathlib.Path("reports").mkdir(exist_ok=True)
    pathlib.Path("reports/results.json").write_text('{"suites": []}')
print("1 failed", flush=True)
sys.exit(1)
'''


class _Server(BaseHTTPRequestHandler):
    jobs: list[dict] = []
    calls: list[tuple[str, dict | bytes]] = []
    cancel = False

    def do_POST(self) -> None:  # noqa: N802
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        path = self.path.split("?")[0]
        is_json = self.headers.get("Content-Type", "").startswith("application/json")
        type(self).calls.append((self.path, json.loads(raw) if is_json and raw else raw))
        if path.endswith("/automation/claim"):
            if not self.jobs:
                self.send_response(204)
                self.end_headers()
                return
            self._json(self.jobs.pop(0))
        elif path.endswith("/progress"):
            self._json({"cancelled": self.cancel})
        elif path.endswith("/finish"):
            self._json({"status": "finished"})
        elif path.endswith("/runs/import-junit"):
            self._json({"run_id": 5, "run_name": "x", "total": 2, "matched": 2, "created": 0,
                        "unmatched": [], "statuses": {"passed": 1, "failed": 1}})

    def _json(self, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a: object) -> None:
        pass


@pytest.fixture
def server():  # type: ignore[no-untyped-def]
    _Server.jobs, _Server.calls, _Server.cancel = [], [], False
    httpd = HTTPServer(("127.0.0.1", 0), _Server)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def _cfg(url: str, tmp_path: Path, extra: str = "") -> AgentConfig:
    script = tmp_path / "fake_tests.py"
    script.write_text(FAKE_TESTS)
    return AgentConfig(url=url, token="th_x", project=3, command=f'"{sys.executable}" "{script}"{extra}',
                       report=Path("reports/results.json"), cwd=tmp_path, name="box",
                       report_url="http://localhost:9323/index.html", poll=0.05, once=True)


def test_case_grep_and_command() -> None:
    assert case_grep([197, 7]) == "(?<![A-Za-z0-9])C(197|7)(?![0-9])"
    cfg = AgentConfig(url="", token="", project=1, command="npx playwright test --project chromium",
                      report=Path("r.json"))
    cmd = build_command(cfg, [5])
    assert cmd[1:] == ["playwright", "test", "--project", "chromium", "--grep", case_grep([5])]
    assert build_command(cfg, [])[-1] == "chromium"  # no grep for "all tests"


def test_runs_selected_cases_and_uploads(server: str, tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "results.json").write_text("stale")  # must be removed before the run
    _Server.jobs = [{"id": 11, "run_id": 5, "case_ids": [197, 198]}]
    assert run_agent(_cfg(server, tmp_path), log=lambda *_: None) == 0

    ran = json.loads((tmp_path / "argv.json").read_text())
    assert ran["argv"] == ["--grep", case_grep([197, 198])] and ran["run"] == "5"
    paths = [p for p, _ in _Server.calls]
    assert paths[0] == "/api/projects/3/automation/claim"
    upload = next(p for p in paths if "/runs/import-junit" in p)
    assert "run_id=5" in upload and "report_url=http%3A%2F%2Flocalhost%3A9323%2Findex.html" in upload
    finish = next(b for p, b in _Server.calls if p.endswith("/finish"))
    assert finish["status"] == "finished" and finish["exit_code"] == 1
    assert "2 tests (1 failed, 1 passed)" in finish["message"]
    logs = "".join(b["log"] for p, b in _Server.calls if p.endswith(("/progress", "/finish")))
    assert "Running 2 tests" in logs and "1 failed" in logs and "--grep" in logs


def test_missing_report_is_an_error(server: str, tmp_path: Path) -> None:
    _Server.jobs = [{"id": 12, "run_id": 6, "case_ids": []}]
    run_agent(_cfg(server, tmp_path, " --no-report"), log=lambda *_: None)
    finish = next(b for p, b in _Server.calls if p.endswith("/finish"))
    assert finish["status"] == "error" and "no report was written" in finish["message"]
    assert not any("/runs/import-junit" in p for p, _ in _Server.calls)
    assert json.loads((tmp_path / "argv.json").read_text())["argv"] == ["--no-report"]  # all tests: no grep


def test_command_that_cannot_start(server: str, tmp_path: Path) -> None:
    _Server.jobs = [{"id": 13, "run_id": 7, "case_ids": []}]
    cfg = _cfg(server, tmp_path)
    cfg.command = "definitely-not-a-real-binary-xyz --flag"
    run_agent(cfg, log=lambda *_: None)
    finish = next(b for p, b in _Server.calls if p.endswith("/finish"))
    assert finish["status"] == "error" and "Could not start" in finish["message"]


def test_cancel_from_testharbor_stops_the_tests(server: str, tmp_path: Path) -> None:
    slow = tmp_path / "slow.py"
    slow.write_text("import time\nprint('start', flush=True)\ntime.sleep(60)\n")
    _Server.jobs = [{"id": 14, "run_id": 8, "case_ids": []}]
    _Server.cancel = True
    cfg = _cfg(server, tmp_path)
    cfg.command = f'"{sys.executable}" "{slow}"'
    run_agent(cfg, log=lambda *_: None)  # returns well before the 60 s sleep ends
    finish = next(b for p, b in _Server.calls if p.endswith("/finish"))
    assert (finish["status"], finish["message"]) == ("error", "Cancelled")
