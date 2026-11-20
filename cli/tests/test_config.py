"""testharbor.toml, `testcli init`, built-in catalogs and how selected tests reach the command."""

import json
import sys
import textwrap
from pathlib import Path

import pytest

from testharbor_cli import agent as agent_mod
from testharbor_cli import collect, config
from testharbor_cli.agent import AgentConfig, build_command
from testharbor_cli.main import CliError, main

from test_agent import _Server, server  # noqa: F401  (fixture; tests/ is on sys.path)


def test_load_config_presets_and_errors(tmp_path: Path) -> None:
    path = tmp_path / "testharbor.json"
    path.write_text(json.dumps({"project": 3, "framework": "playwright", "env": {"X": "1"}}))
    conf = config.load_config(path)
    assert conf["select"] == "grep" and conf["catalog"] == "auto" and conf["report"] == "reports/results.json"
    assert conf["env"] == {"PLAYWRIGHT_JSON_OUTPUT_NAME": "reports/results.json", "PLAYWRIGHT_HTML_OPEN": "never",
                           "X": "1"}
    for bad, msg in (({"token": "x"}, "unknown setting 'token'"), ({"framework": "jest"}, "framework"),
                     ({"select": "magic", "command": "x", "report": "r"}, "select"), ({}, "set `command`")):
        path.write_text(json.dumps(bad))
        with pytest.raises(CliError, match=msg):
            config.load_config(path)
    if sys.version_info >= (3, 11):
        toml = tmp_path / "testharbor.toml"
        toml.write_text('[testharbor]\nframework = "pytest"\nproject = 4\n')
        assert config.load_config(toml)["select"] == "args"


def test_find_config_and_dotenv(tmp_path: Path) -> None:
    (tmp_path / "testharbor.json").write_text("{}")
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert config.find_config(deep) == tmp_path / "testharbor.json"
    (tmp_path / ".env").write_text(textwrap.dedent("""\
        SA_PASSWORD=secret
        TESTHARBOR_TOKEN="th_x"
        export TESTHARBOR_URL=http://h
        TESTHARBOR_PROJECT=
        # TESTHARBOR_NAME=n
        TESTHARBOR_EVIL=$(touch pwned)
    """))
    assert config.read_dotenv(tmp_path) == {"TESTHARBOR_TOKEN": "th_x", "TESTHARBOR_URL": "http://h",
                                            "TESTHARBOR_EVIL": "$(touch pwned)"}
    assert not (tmp_path / "pwned").exists()


def test_init_detects_the_framework(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "playwright.config.ts").write_text("")
    assert config.detect_framework(tmp_path) == "playwright"
    assert main(["init", "--cwd", str(tmp_path), "--project", "7", "--url", "http://th"]) == 0
    text = (tmp_path / "testharbor.toml").read_text()
    assert 'framework = "playwright"' in text and "project = 7" in text and "TOKEN" not in text.split("\n", 2)[2].split("=")[0]
    assert main(["init", "--cwd", str(tmp_path)]) == 2  # exists
    py = tmp_path / "py"
    py.mkdir()
    (py / "conftest.py").write_text("")
    (py / "uv.lock").write_text("")
    assert config.detect_framework(py) == "pytest"
    assert 'command = "uv run pytest --junitxml=reports/junit.xml"' in config.init_text(py, "", None)


def test_playwright_catalog_and_grep() -> None:
    listing = {"suites": [{"title": "auth.spec.ts", "file": "auth.spec.ts", "specs": [
        {"title": "logs in", "file": "auth.spec.ts", "tags": ["@smoke", "@C12"]},
    ], "suites": [{"title": "Logout", "specs": [
        {"title": "logs out (a)", "file": "auth.spec.ts", "tags": []},
        {"title": "logs out (a)", "file": "auth.spec.ts", "tags": []},  # a second project: same test
    ]}]}]}
    tests = collect.playwright_catalog_from_list(listing)
    assert [(t["key"], t["path"], t["tags"], t["case_ids"]) for t in tests] == [
        ("auth.spec.ts::logs in", ["auth.spec.ts"], ["smoke"], [12]),
        ("auth.spec.ts::Logout › logs out (a)", ["auth.spec.ts", "Logout"], [], []),
    ]
    regex = collect.grep_for_keys(["auth.spec.ts::Logout › logs out (a)"], [12])
    import re
    assert re.search(regex, "chromium auth.spec.ts Logout logs out (a)")
    assert not re.search(regex, "chromium auth.spec.ts Logout logs out (b)")
    assert re.search(regex, "auth.spec.ts other @C12")


def test_pytest_catalog_from_ids() -> None:
    tests = collect.pytest_catalog_from_ids([
        "tests/api/test_auth.py::TestLogin::test_valid_password[a]",
        "tests/api/test_auth.py::TestLogin::test_valid_password[b]",
        "tests/test_misc.py::test_signup_C150",
    ])
    assert [(t["key"], t["title"], t["path"], t["case_ids"]) for t in tests] == [
        ("tests/api/test_auth.py::TestLogin::test_valid_password", "Valid password",
         ["tests", "api", "test_auth", "TestLogin"], []),
        ("tests/test_misc.py::test_signup_C150", "Signup C150", ["tests", "test_misc"], [150]),
    ]


def test_select_modes() -> None:
    cfg = AgentConfig(url="", token="", project=1, command="pytest -q", report=Path("r.xml"), select="args")
    assert build_command(cfg, [5, 6], ["t.py::test_a"])[1:] == ["-q", "t.py::test_a"]
    with pytest.raises(CliError, match="sync the autotests"):
        build_command(cfg, [5], [])
    cfg.select = "env"
    assert build_command(cfg, [5], ["t.py::test_a"])[1:] == ["-q"]
    cfg.select, cfg.command = "grep", "npx playwright test"
    assert build_command(cfg, [5], [])[-1] == agent_mod.case_grep([5])
    assert build_command(cfg, [], [])[-1] == "test"


def test_agent_from_testharbor_toml_runs_selected_pytest_tests(server: str, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """A real pytest project: catalog built in, the selected test runs as a node id, JUnit uploaded."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_shop.py").write_text(textwrap.dedent("""\
        import pytest

        def test_cart_is_empty():
            pass

        @pytest.mark.parametrize("card", ["visa", "amex"])
        def test_pay_by_card(card):
            assert card == "visa"
    """))
    (tmp_path / "testharbor.json").write_text(json.dumps({
        "url": server, "project": 3, "framework": "pytest", "name": "box",
        "command": f"{sys.executable} -m pytest -p no:cacheprovider --junitxml=reports/junit.xml",
    }))
    (tmp_path / ".env").write_text("TESTHARBOR_TOKEN=th_from_dotenv\n")
    monkeypatch.delenv("TESTHARBOR_TOKEN", raising=False)
    monkeypatch.delenv("TESTHARBOR_URL", raising=False)
    monkeypatch.delenv("TESTHARBOR_PROJECT", raising=False)
    _Server.jobs = [{"id": 40, "run_id": 2, "case_ids": [9],
                     "automation_keys": ["tests/test_shop.py::test_pay_by_card"]}]
    assert main(["agent", "--cwd", str(tmp_path), "--once", "--poll", "0.05"]) == 0

    put_path, catalog = next((p, b) for p, b in _Server.calls if p.endswith("/automation/catalog"))
    assert put_path == "/api/projects/3/automation/catalog"
    assert [t["key"] for t in catalog["tests"]] == ["tests/test_shop.py::test_cart_is_empty",
                                                     "tests/test_shop.py::test_pay_by_card"]
    claim = next(b for p, b in _Server.calls if p.endswith("/automation/claim"))
    assert claim["info"]["mode"] == "local" and claim["info"]["framework"] == "pytest"
    logs = "".join(b["log"] for p, b in _Server.calls if p.endswith(("/progress", "/finish")))
    assert "tests/test_shop.py::test_pay_by_card" in logs.splitlines()[0]  # node id appended
    assert "1 failed, 1 passed" in logs  # only the 2 parametrized runs, not test_cart_is_empty
    upload = next(b for p, b in _Server.calls if "/runs/import-junit" in p)
    assert b"test_pay_by_card[amex]" in upload and b"test_cart_is_empty" not in upload


def test_secrets_run_for_local_agents_only(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "testharbor.json").write_text(json.dumps({
        "url": "http://127.0.0.1:9", "project": 1, "framework": "pytest",
        "secrets": [f"{sys.executable} -c \"open('secrets-ran', 'w').write('1')\""],
    }))
    monkeypatch.setenv("TESTHARBOR_TOKEN", "th_x")
    started: list[object] = []
    monkeypatch.setattr("testharbor_cli.agent.run_agent", lambda cfg, log=print: started.append(cfg) or 0)
    assert main(["agent", "--cwd", str(tmp_path)]) == 0
    assert (tmp_path / "secrets-ran").exists() and started
    (tmp_path / "secrets-ran").unlink()
    assert main(["agent", "--cwd", str(tmp_path), "--no-secrets"]) == 0
    assert not (tmp_path / "secrets-ran").exists()
    conf = json.loads((tmp_path / "testharbor.json").read_text())
    conf["secrets"] = f"{sys.executable} -c \"raise SystemExit(4)\""
    (tmp_path / "testharbor.json").write_text(json.dumps(conf))
    assert main(["agent", "--cwd", str(tmp_path)]) == 2  # failed secrets: the agent does not start
