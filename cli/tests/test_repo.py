"""Server agents: a branch of a git repository in a clean checkout."""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from test_agent import _Server, server  # noqa: F401  (fixture; tests/ is on sys.path)
from testharbor_cli.repo import RepoAgent, display_url, find_branch_config, run_repo_agent


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                               "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin",
                               "HOME": str(cwd)}).stdout.strip()


def make_origin(tmp: Path) -> Path:
    origin = tmp / "origin.git"
    git(tmp, "init", "--bare", "-b", "main", str(origin))
    work = tmp / "work"
    git(tmp, "clone", str(origin), str(work))
    qa = work / "qa"
    (qa / "tests").mkdir(parents=True)
    (qa / "tests" / "test_shop.py").write_text(textwrap.dedent("""\
        import pathlib

        def test_cart():
            pass

        def test_secret_is_there():
            assert "APP_PASSWORD=s3cret" in pathlib.Path(".env").read_text()
            assert pathlib.Path("config/creds.ini").read_text() == "key=1"
    """))
    (qa / "testharbor.json").write_text(json.dumps({
        "framework": "pytest",
        "command": f"{sys.executable} -m pytest -p no:cacheprovider --junitxml=reports/junit.xml",
        "setup": [f"{sys.executable} -c \"open('setup-ran', 'w').write('1')\""],
    }))
    git(work, "add", "-A")
    git(work, "commit", "-m", "tests")
    git(work, "push", "origin", "main")
    git(work, "checkout", "-b", "feature/x")
    (qa / "tests" / "test_new.py").write_text("def test_only_on_the_branch():\n    pass\n")
    git(work, "add", "-A")
    git(work, "commit", "-m", "new test")
    git(work, "push", "origin", "feature/x")
    return origin


def test_display_url() -> None:
    assert display_url("https://user:pw@bitbucket.org/team/qa.git") == "bitbucket.org/team/qa"
    assert display_url("git@bitbucket.org:team/qa.git") == "bitbucket.org/team/qa"


def test_runs_the_selected_test_of_a_branch(server: str, tmp_path: Path) -> None:  # noqa: F811
    origin = make_origin(tmp_path)
    secrets = tmp_path / "tests.env"
    secrets.write_text("APP_PASSWORD=s3cret\n")
    (tmp_path / "files" / "config").mkdir(parents=True)
    (tmp_path / "files" / "config" / "creds.ini").write_text("key=1")
    _Server.jobs = [{"id": 51, "run_id": 4, "case_ids": [7, 8], "branch": "feature/x",
                     "automation_keys": ["tests/test_new.py::test_only_on_the_branch",
                                         "tests/test_shop.py::test_secret_is_there"]}]
    ra = RepoAgent(url=server, token="th_x", project=3, repo=str(origin), workdir=tmp_path / "agent",
                   name="srv", env_file=secrets, secret_files=tmp_path / "files", poll=0.05, once=True)
    assert run_repo_agent(ra, log=lambda *_: None) == 0

    # The catalog comes from the default branch: no test_only_on_the_branch there.
    catalog = next(b for p, b in _Server.calls if p.endswith("/automation/catalog"))
    assert [t["key"] for t in catalog["tests"]] == ["tests/test_shop.py::test_cart",
                                                     "tests/test_shop.py::test_secret_is_there"]
    claim = next(b for p, b in _Server.calls if p.endswith("/automation/claim"))
    assert claim["info"]["mode"] == "repo" and claim["info"]["default_branch"] == "main"
    assert set(claim["info"]["branches"]) == {"main", "feature/x"}
    logs = "".join(b["log"] for p, b in _Server.calls if p.endswith(("/progress", "/finish")))
    assert "Checked out feature/x at" in logs and "setup-ran" in logs
    assert "2 passed" in logs  # the branch's new test and the one reading the copied .env
    upload_path, body = next((p, b) for p, b in _Server.calls if "/runs/import-junit" in p)
    assert "branch=feature%2Fx" in upload_path and b"test_only_on_the_branch" in body and b"test_cart" not in body
    finish = next(b for p, b in _Server.calls if p.endswith("/finish"))
    assert finish["status"] == "finished"
    assert list((tmp_path / "agent" / "runs").iterdir()) == []  # checkouts removed


def test_unknown_branch_fails_the_job(server: str, tmp_path: Path) -> None:  # noqa: F811
    origin = make_origin(tmp_path)
    _Server.jobs = [{"id": 52, "run_id": 4, "case_ids": [], "branch": "nope"}]
    ra = RepoAgent(url=server, token="th_x", project=3, repo=str(origin), workdir=tmp_path / "agent",
                   name="srv", poll=0.05, once=True)
    run_repo_agent(ra, log=lambda *_: None)
    finish = next(b for p, b in _Server.calls if p.endswith("/finish"))
    assert finish["status"] == "error" and "branch 'nope' is not in" in finish["message"]


def test_find_branch_config(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "testharbor.toml").write_text("")
    assert find_branch_config(tmp_path) == tmp_path / "a" / "testharbor.toml"
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "testharbor.toml").write_text("")
    import pytest
    from testharbor_cli.main import CliError
    with pytest.raises(CliError, match="several"):
        find_branch_config(tmp_path)
    assert find_branch_config(tmp_path, "b") == tmp_path / "b" / "testharbor.toml"
