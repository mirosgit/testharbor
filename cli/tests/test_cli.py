import json
import threading
from email import message_from_bytes
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from testharbor_cli import ci_env
from testharbor_cli.main import EXIT_UNMATCHED, EXIT_USAGE, main

RESPONSE = {
    "run_id": 7, "run_name": "Nightly #123", "total": 3, "matched": 2, "created": 0,
    "unmatched": [{"name": "test_x", "classname": "tests.t", "reason": "no case"}],
    "statuses": {"passed": 2},
}


class _Handler(BaseHTTPRequestHandler):
    calls: list[dict] = []
    status = 200

    def do_POST(self) -> None:  # noqa: N802
        body = self.rfile.read(int(self.headers["Content-Length"]))
        msg = message_from_bytes(
            f"Content-Type: {self.headers['Content-Type']}\r\n\r\n".encode() + body
        )
        files = [(p.get_filename(), p.get_payload(decode=True)) for p in msg.get_payload()]
        type(self).calls.append({"path": self.path, "auth": self.headers["Authorization"], "files": files})
        payload = RESPONSE if self.status == 200 else {"detail": "Not authenticated"}
        data = json.dumps(payload).encode()
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a: object) -> None:
        pass


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    _Handler.calls = []
    _Handler.status = 200
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    for k in list(__import__("os").environ):
        if k.startswith(("GITHUB_", "BITBUCKET_", "GITLAB_", "CI_", "TESTHARBOR_", "JENKINS_")):
            monkeypatch.delenv(k)
    monkeypatch.setenv("TESTHARBOR_URL", f"http://127.0.0.1:{httpd.server_port}")
    monkeypatch.setenv("TESTHARBOR_TOKEN", "th_secret")
    yield _Handler
    httpd.shutdown()


@pytest.fixture
def reports(tmp_path: Path) -> Path:
    (tmp_path / "a.xml").write_text("<testsuite/>")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.xml").write_text("<testsuite/>")
    (tmp_path / "notes.txt").write_text("x")
    return tmp_path


def test_upload_sends_files_params_and_token(server, reports, capsys) -> None:  # type: ignore[no-untyped-def]
    code = main(["upload", str(reports / "a.xml"), "--project", "3", "--run-name", "Nightly #123",
                 "--branch", "main", "--commit", "abc123", "--auto-create"])
    assert code == 0
    call = server.calls[0]
    assert call["auth"] == "Bearer th_secret"
    assert call["path"].startswith("/api/projects/3/runs/import-junit?")
    assert "run_name=Nightly+%23123" in call["path"] and "branch=main" in call["path"]
    assert "commit=abc123" in call["path"] and "auto_create=true" in call["path"]
    assert call["files"] == [("a.xml", b"<testsuite/>")]
    out = capsys.readouterr().out
    assert "run #7" in out and "unmatched: 1" in out and "/projects/3/runs/7" in out


def test_globs_and_directories(server, reports) -> None:  # type: ignore[no-untyped-def]
    assert main(["upload", str(reports / "*.xml"), str(reports / "sub"), "-p", "1"]) == 0
    assert [f[0] for f in server.calls[0]["files"]] == ["a.xml", "b.xml"]


def test_missing_config(server, reports, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("TESTHARBOR_TOKEN")
    assert main(["upload", str(reports / "a.xml"), "-p", "1"]) == EXIT_USAGE
    assert "TESTHARBOR_TOKEN" in capsys.readouterr().err


def test_missing_file(server, tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["upload", str(tmp_path / "nope.xml"), "-p", "1"]) == 1
    assert "File not found" in capsys.readouterr().err


def test_http_error_is_reported(server, reports, capsys) -> None:  # type: ignore[no-untyped-def]
    server.status = 401
    assert main(["upload", str(reports / "a.xml"), "-p", "1"]) == 1
    assert "HTTP 401: Not authenticated (check TESTHARBOR_TOKEN)" in capsys.readouterr().err


def test_fail_on_unmatched_and_json(server, reports, capsys) -> None:  # type: ignore[no-untyped-def]
    code = main(["upload", str(reports / "a.xml"), "-p", "1", "--fail-on-unmatched", "--json"])
    assert code == EXIT_UNMATCHED
    assert json.loads(capsys.readouterr().out)["run_id"] == 7


def test_ci_detection_fills_defaults(server, reports, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    monkeypatch.setenv("GITHUB_SHA", "deadbeef")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/shop")
    monkeypatch.setenv("GITHUB_RUN_ID", "99")
    monkeypatch.setenv("GITHUB_RUN_NUMBER", "12")
    assert main(["upload", str(reports / "a.xml"), "-p", "1", "--branch", "override"]) == 0
    path = server.calls[0]["path"]
    assert "branch=override" in path and "commit=deadbeef" in path
    assert "run_name=GitHub+Actions+%2312" in path
    assert "build_url=https%3A%2F%2Fgithub.com%2Facme%2Fshop%2Factions%2Fruns%2F99" in path


def test_ci_env_bitbucket() -> None:
    env = {"BITBUCKET_BUILD_NUMBER": "41", "BITBUCKET_BRANCH": "develop", "BITBUCKET_COMMIT": "abc",
           "BITBUCKET_GIT_HTTP_ORIGIN": "http://bitbucket.org/acme/shop"}
    assert ci_env.detect(env) == {
        "ci": "Bitbucket Pipelines", "branch": "develop", "commit": "abc",
        "build_url": "http://bitbucket.org/acme/shop/pipelines/results/41", "build": "41",
    }
    assert ci_env.detect({}) == {}
