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
    gone = False  # the job's run was deleted: progress answers 404

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
            if self.gone:
                self.send_response(404)
                self.end_headers()
                return
            self._json({"cancelled": self.cancel})
        elif path.endswith("/finish"):
            self._json({"status": "finished"})
        elif path.endswith("/runs/import-junit"):
            self._json({"run_id": 5, "run_name": "x", "total": 2, "matched": 2, "created": 0,
                        "unmatched": [], "statuses": {"passed": 1, "failed": 1}})

    def do_PUT(self) -> None:  # noqa: N802
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if "/report" in self.path:  # an HTML report (multipart zip)
            type(self).calls.append((self.path, raw))
            self._json({"id": 1})
            return
        type(self).calls.append((self.path, json.loads(raw)))
        self._json({"counts": {"create": 2, "update": 0, "link": 0, "outdated": 0, "unchanged": 1}})

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
    _Server.jobs, _Server.calls, _Server.cancel, _Server.gone = [], [], False, False
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


# A stand-in for a runner with one process per role: reads its run options from the environment,
# writes one JUnit file per role under reports/t<job id>/.
ROLE_RUNNER = r'''
import json, os, pathlib
env = {k: os.environ.get(k) for k in ("ENV", "ROLES", "HEADED", "TESTHARBOR_CASE_IDS", "TESTHARBOR_TOKEN")}
env["selection"] = json.loads(pathlib.Path(os.environ["TESTHARBOR_SELECTION"]).read_text())
pathlib.Path("env.json").write_text(json.dumps(env))
for role in os.environ["ROLES"].split():
    folder = pathlib.Path(f"reports/t{os.environ['TESTHARBOR_JOB_ID']}/{role}")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "junit.xml").write_text("<testsuites/>")
'''

OPTIONS = {"options": [
    {"name": "ENV", "label": "Environment", "type": "choice", "choices": ["dev", "qa"], "default": "dev"},
    {"name": "ROLES", "label": "Roles", "type": "multi",
     "choices": [{"value": "admin", "label": "Admin"}, {"value": "support_agent", "label": "Support Agent"}]},
    {"name": "HEADED", "type": "bool"},
]}


def test_load_options_normalizes_and_rejects(tmp_path: Path) -> None:
    path = tmp_path / "options.json"
    path.write_text(json.dumps(OPTIONS))
    env, roles, headed = agent_mod.load_options(path)
    assert env["choices"] == [{"value": "dev", "label": "dev"}, {"value": "qa", "label": "qa"}]
    assert (roles["default"], headed["default"], headed["label"]) == ([], False, "HEADED")
    for bad in ({"name": "PATH", "type": "choice", "choices": ["x"]}, {"name": "env", "type": "bool"},
                {"name": "X", "type": "text"}, {"name": "X", "type": "choice"},
                {"name": "X", "type": "choice", "choices": ["a"], "default": "b"}):
        path.write_text(json.dumps({"options": [bad]}))
        with pytest.raises(agent_mod.CliError):
            agent_mod.load_options(path)


def test_option_env_checks_values(tmp_path: Path) -> None:
    path = tmp_path / "options.json"
    path.write_text(json.dumps(OPTIONS))
    options = agent_mod.load_options(path)
    assert agent_mod.option_env(options, {}) == {"ENV": "dev", "ROLES": "", "HEADED": "0"}
    assert agent_mod.option_env(options, {"ENV": "qa", "ROLES": ["support_agent", "admin"], "HEADED": True}) == {
        "ENV": "qa", "ROLES": "support_agent admin", "HEADED": "1"}
    for bad in ({"ENV": "prod"}, {"ROLES": ["root"]}, {"ROLES": "admin"}, {"HEADED": "1"}, {"PATH": "/tmp"}):
        with pytest.raises(agent_mod.CliError):
            agent_mod.option_env(options, bad)
    with pytest.raises(agent_mod.CliError, match="without --options"):
        agent_mod.option_env([], {"ENV": "qa"})


def test_job_with_run_options_and_a_report_per_role(server: str, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TESTHARBOR_TOKEN", "th_secret")
    script = tmp_path / "runner.py"
    script.write_text(ROLE_RUNNER)
    stale = tmp_path / "reports" / "t21" / "viewer"
    stale.mkdir(parents=True)
    (stale / "junit.xml").write_text("<testsuites/>")  # left from an earlier database: not uploaded
    import os
    os.utime(stale / "junit.xml", (1, 1))
    (tmp_path / "options.json").write_text(json.dumps(OPTIONS))
    _Server.jobs = [{"id": 21, "run_id": 9, "case_ids": [142], "automation_keys": ["t.py::test_a"],
                     "params": {"ENV": "qa", "ROLES": ["admin", "support_agent"]}}]
    cfg = AgentConfig(url=server, token="th_x", project=3, command=f'"{sys.executable}" "{script}"',
                      report=Path("reports/t{job_id}/*/junit.xml"), cwd=tmp_path, name="box", grep_arg="",
                      report_url="http://localhost:9323/t{job_id}/index.html", poll=0.05, once=True,
                      options=agent_mod.load_options(tmp_path / "options.json"))
    assert run_agent(cfg, log=lambda *_: None) == 0

    env = json.loads((tmp_path / "env.json").read_text())
    assert env == {"ENV": "qa", "ROLES": "admin support_agent", "HEADED": "0", "TESTHARBOR_CASE_IDS": "142",
                   "TESTHARBOR_TOKEN": None, "selection": {"case_ids": [142], "automation_keys": ["t.py::test_a"]}}
    claim = next(b for p, b in _Server.calls if p.endswith("/automation/claim"))
    assert [o["name"] for o in claim["options"]] == ["ENV", "ROLES", "HEADED"]
    upload_path, body = next((p, b) for p, b in _Server.calls if "/runs/import-junit" in p)
    assert "report_url=http%3A%2F%2Flocalhost%3A9323%2Ft21%2Findex.html" in upload_path
    assert body.count(b'filename="junit.xml"') == 2  # admin + support_agent, not the stale viewer file
    finish = next(b for p, b in _Server.calls if p.endswith("/finish"))
    assert finish["status"] == "finished"
    logs = "".join(b["log"] for p, b in _Server.calls if p.endswith(("/progress", "/finish")))
    assert "ENV=qa ROLES='admin support_agent' HEADED=0 $ " in logs


def test_job_with_an_option_the_agent_does_not_offer(server: str, tmp_path: Path) -> None:
    _Server.jobs = [{"id": 22, "run_id": 9, "case_ids": [], "params": {"ENV": "prod"}}]
    cfg = _cfg(server, tmp_path)
    (tmp_path / "options.json").write_text(json.dumps(OPTIONS))
    cfg.options = agent_mod.load_options(tmp_path / "options.json")
    run_agent(cfg, log=lambda *_: None)
    finish = next(b for p, b in _Server.calls if p.endswith("/finish"))
    assert finish["status"] == "error" and "'prod' is not offered by this agent" in finish["message"]
    assert not (tmp_path / "argv.json").exists()  # nothing ran


def test_catalog_is_sent_when_the_agent_starts(server: str, tmp_path: Path) -> None:
    (tmp_path / "catalog.json").write_text(json.dumps({"tests": [{"key": "a", "title": "A"}]}))
    cfg = _cfg(server, tmp_path)
    cfg.catalog = tmp_path / "catalog.json"
    lines: list[str] = []
    _Server.jobs = [{"id": 30, "run_id": 1, "case_ids": []}]
    run_agent(cfg, log=lines.append)
    path, body = _Server.calls[0]
    assert path == "/api/projects/3/automation/catalog" and body == {"agent": "box", "tests": [{"key": "a", "title": "A"}]}
    assert any("1 tests sent (2 create)" in line and "Sync autotests" in line for line in lines)

    cfg.catalog = tmp_path / "missing.json"
    lines.clear()
    assert agent_mod.upload_catalog(cfg, agent_mod.Api(cfg), log=lines.append) is False
    assert "catalog not sent" in lines[0]


def test_deleted_run_stops_the_tests(server: str, tmp_path: Path) -> None:
    slow = tmp_path / "slow.py"
    slow.write_text("import time\nprint('start', flush=True)\ntime.sleep(60)\n")
    _Server.jobs = [{"id": 15, "run_id": 8, "case_ids": []}]
    _Server.gone = True
    cfg = _cfg(server, tmp_path)
    cfg.command = f'"{sys.executable}" "{slow}"'
    lines: list[str] = []
    run_agent(cfg, log=lines.append)  # returns well before the 60 s sleep ends
    assert any("run was deleted" in line for line in lines)
