"""testcli: upload test results to TestHarbor, or run tests on request from it.

    export TESTHARBOR_URL=https://testharbor.example.com
    export TESTHARBOR_TOKEN=th_...
    testcli upload junit.xml --project 1 --run-name "Nightly #123" --branch main --commit abc123
    testcli agent --project 1 --command "npx playwright test" --report reports/results.json
    testcli init && testcli agent           # settings from testharbor.toml
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from . import __version__
from .ci_env import detect

EXIT_ERROR, EXIT_USAGE, EXIT_UNMATCHED = 1, 2, 3


class CliError(Exception):
    pass


def _multipart(files: list[Path]) -> tuple[bytes, str]:
    boundary = f"----testharbor{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for path in files:
        name = path.name.replace('"', "")
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            f"Content-Type: application/xml\r\n\r\n".encode()
        )
        parts.append(path.read_bytes())
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def upload(base_url: str, token: str, project: int, files: list[Path], params: dict[str, str],
           timeout: float = 120) -> dict:
    body, content_type = _multipart(files)
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    url = f"{base_url.rstrip('/')}/api/projects/{project}/runs/import-junit?{query}"
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
        "Accept": "application/json",
        "User-Agent": f"testharbor-cli/{__version__}",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("detail", detail)
        except (ValueError, AttributeError):
            pass
        hint = " (check TESTHARBOR_TOKEN)" if e.code == 401 else ""
        raise CliError(f"HTTP {e.code}: {detail}{hint}") from e
    except urllib.error.URLError as e:
        raise CliError(f"Cannot reach {base_url}: {e.reason}") from e


def _expand(patterns: list[str]) -> list[Path]:
    """Expand globs ourselves too (shells on Windows/CI YAML may not)."""
    out: list[Path] = []
    for p in patterns:
        matches = sorted(glob.glob(p, recursive=True)) if glob.has_magic(p) else [p]
        for m in matches:
            path = Path(m)
            if path.is_dir():
                out += sorted(path.rglob("*.xml"))
            elif path.is_file():
                out.append(path)
            else:
                raise CliError(f"File not found: {m}")
    if not out:
        raise CliError(f"No files match: {' '.join(patterns)}")
    return list(dict.fromkeys(out))


def cmd_upload(args: argparse.Namespace) -> int:
    url = args.url or os.environ.get("TESTHARBOR_URL", "")
    token = args.token or os.environ.get("TESTHARBOR_TOKEN", "")
    project = args.project or os.environ.get("TESTHARBOR_PROJECT", "")
    missing = [n for n, v in (("TESTHARBOR_URL (or --url)", url), ("TESTHARBOR_TOKEN (or --token)", token),
                              ("--project (or TESTHARBOR_PROJECT)", project)) if not v]
    if missing:
        print(f"error: missing {', '.join(missing)}", file=sys.stderr)
        return EXIT_USAGE
    try:
        project_id = int(project)
    except ValueError:
        print(f"error: --project must be a numeric project id, got {project!r}", file=sys.stderr)
        return EXIT_USAGE

    ci = {} if args.no_ci_detect else detect()
    run_name = args.run_name
    if not run_name and ci.get("ci"):
        run_name = f"{ci['ci']} #{ci['build']}" if ci.get("build") else ci["ci"]
    params = {
        "run_name": run_name or "",
        "description": args.description or "",
        "branch": args.branch or ci.get("branch", ""),
        "commit": args.commit or ci.get("commit", ""),
        "build_url": args.build_url or ci.get("build_url", ""),
        "report_url": args.report_url or os.environ.get("TESTHARBOR_REPORT_URL", ""),
        "auto_create": "true" if args.auto_create else "",
        "run_id": str(args.run_id) if args.run_id else "",
    }
    try:
        files = _expand(args.files)
        result = upload(url, token, project_id, files, params)
    except CliError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_ERROR

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        st = result.get("statuses", {})
        counts = ", ".join(f"{v} {k}" for k, v in sorted(st.items())) or "no results"
        print(f"Uploaded {len(files)} file(s), {result['total']} tests -> run #{result['run_id']} "
              f"\"{result['run_name']}\"")
        print(f"  matched: {result['matched']}  created: {result['created']}  "
              f"unmatched: {len(result['unmatched'])}  ({counts})")
        for u in result["unmatched"][:20]:
            name = f"{u['classname']}::{u['name']}" if u["classname"] else u["name"]
            print(f"  ? {name} - {u['reason']}")
        if len(result["unmatched"]) > 20:
            print(f"  … and {len(result['unmatched']) - 20} more")
        print(f"  {url.rstrip('/')}/projects/{project_id}/runs/{result['run_id']}")
    if args.fail_on_unmatched and result["unmatched"]:
        return EXIT_UNMATCHED
    return 0


def _connection(args: argparse.Namespace) -> tuple[str, str, int] | int:
    url = args.url or os.environ.get("TESTHARBOR_URL", "")
    token = args.token or os.environ.get("TESTHARBOR_TOKEN", "")
    project = args.project or os.environ.get("TESTHARBOR_PROJECT", "")
    missing = [n for n, v in (("TESTHARBOR_URL (or --url)", url), ("TESTHARBOR_TOKEN (or --token)", token),
                              ("--project (or TESTHARBOR_PROJECT)", project)) if not v]
    if missing:
        print(f"error: missing {', '.join(missing)}", file=sys.stderr)
        return EXIT_USAGE
    try:
        return url, token, int(project)
    except ValueError:
        print(f"error: --project must be a numeric project id, got {project!r}", file=sys.stderr)
        return EXIT_USAGE


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return EXIT_USAGE


def cmd_repo_agent(args: argparse.Namespace) -> int:
    """`testcli agent --repo URL`: a server agent running branches of a repository."""
    import re
    import socket

    from .config import read_dotenv
    from .repo import RepoAgent, display_url, run_repo_agent

    dotenv = read_dotenv(Path.cwd())

    def env(name: str) -> str:
        return os.environ.get(name) or dotenv.get(name, "")

    url = args.url or env("TESTHARBOR_URL")
    token = args.token or env("TESTHARBOR_TOKEN")
    project = args.project or env("TESTHARBOR_PROJECT")
    repo = args.repo or env("TESTHARBOR_REPO")
    missing = [n for n, v in (("TESTHARBOR_URL", url), ("TESTHARBOR_TOKEN", token), ("TESTHARBOR_PROJECT", project))
               if not v]
    if missing:
        return _fail(f"missing {', '.join(missing)}")
    if not project.isdigit():
        return _fail(f"project must be a numeric project id, got {project!r}")
    env_file = args.env_file or env("TESTHARBOR_TESTS_ENV")
    if env_file and not Path(env_file).is_file():
        return _fail(f"--env-file {env_file} not found (the tests' .env with their passwords)")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", display_url(repo)).strip("-") or "repo"
    workdir = Path(args.workdir or env("TESTHARBOR_WORKDIR") or Path.home() / ".cache" / "testharbor" / slug)
    if "TESTHARBOR_GIT_TOKEN" not in os.environ and dotenv.get("TESTHARBOR_GIT_TOKEN"):
        os.environ["TESTHARBOR_GIT_TOKEN"] = dotenv["TESTHARBOR_GIT_TOKEN"]  # read by git through GIT_ASKPASS
    if "TESTHARBOR_GIT_USER" not in os.environ and dotenv.get("TESTHARBOR_GIT_USER"):
        os.environ["TESTHARBOR_GIT_USER"] = dotenv["TESTHARBOR_GIT_USER"]
    return run_repo_agent(RepoAgent(
        url=url, token=token, project=int(project), repo=repo, workdir=workdir,
        name=args.name or env("TESTHARBOR_AGENT_NAME") or f"{socket.gethostname()} (server)",
        env_file=Path(env_file) if env_file else None,
        secret_files=Path(sf) if (sf := args.secret_files or env("TESTHARBOR_SECRET_FILES")) else None,
        branch=args.branch or env("TESTHARBOR_BRANCH"),
        subdir=args.repo_path or env("TESTHARBOR_REPO_PATH"), poll=args.poll or 3.0, once=args.once,
        reports_url=env("TESTHARBOR_REPORTS_URL"), reports_port=int(env("TESTHARBOR_REPORTS_PORT") or 9323),
    ))


def cmd_agent(args: argparse.Namespace) -> int:
    from .agent import AgentConfig, load_options, run_agent
    from .config import find_config, load_config, read_dotenv

    if args.repo or os.environ.get("TESTHARBOR_REPO"):
        return cmd_repo_agent(args)
    start = Path(args.cwd or ".").resolve()
    if not start.is_dir():
        return _fail(f"--cwd {args.cwd} is not a directory")
    try:
        path = Path(args.config).resolve() if args.config else find_config(start)
        conf = load_config(path) if path else {}
    except (OSError, CliError) as e:
        return _fail(str(e))
    root = path.parent if path else start
    cwd = Path(args.cwd).resolve() if args.cwd else root
    dotenv = read_dotenv(root)

    def setting(flag: object, key: str, env: str = "", default: object = None) -> object:
        """A flag wins, then the environment, then testharbor.toml, then .env, then the default."""
        for value in (flag, os.environ.get(env) if env else None, conf.get(key), dotenv.get(env) if env else None):
            if value not in (None, ""):
                return value
        return default

    url = str(setting(args.url, "url", "TESTHARBOR_URL", ""))
    token = args.token or os.environ.get("TESTHARBOR_TOKEN") or dotenv.get("TESTHARBOR_TOKEN", "")
    project = setting(args.project, "project", "TESTHARBOR_PROJECT", "")
    missing = [n for n, v in (("url (TESTHARBOR_URL, --url or testharbor.toml)", url),
                              ("TESTHARBOR_TOKEN (environment or .env)", token),
                              ("project (TESTHARBOR_PROJECT, --project or testharbor.toml)", project)) if not v]
    if missing:
        hint = "" if path else " — or run `testcli init` to write a testharbor.toml"
        return _fail(f"missing {', '.join(missing)}{hint}")
    try:
        project_id = int(str(project))
    except ValueError:
        return _fail(f"project must be a numeric project id, got {project!r}")

    legacy_grep = args.grep_arg if args.grep_arg is not None else "--grep"
    select = str(setting(args.select, "select", default=""))
    if not select and args.grep_arg is not None and not args.grep_arg:
        select = "none"  # --grep-arg "": append nothing
    options_file = setting(args.options, "options")
    try:
        options = load_options(cwd / str(options_file)) if options_file and not conf.get("prepare") else []
    except CliError as e:
        return _fail(str(e))
    catalog = setting(args.catalog, "catalog")
    cfg = AgentConfig(
        url=url, token=token, project=project_id,
        command=str(setting(args.command, "command", default="npx playwright test")),
        report=Path(str(setting(args.report, "report", default="reports/results.json"))), cwd=cwd,
        options=options, options_file=Path(str(options_file)) if options_file else None,
        catalog=str(catalog) if catalog else None,
        framework=str(conf.get("framework", "custom")), select=select, prepare=str(conf.get("prepare", "")),
        extra_env=dict(conf.get("env", {})),
        report_url=str(setting(args.report_url, "report_url", "TESTHARBOR_REPORT_URL", "")),
        report_html=str(conf.get("report_html", "")), report_port=int(conf.get("report_port", 9323)),
        auto_create=bool(args.auto_create or conf.get("auto_create")),
        grep_arg=str(conf.get("grep_arg", legacy_grep)) if args.grep_arg is None else args.grep_arg,
        poll=float(args.poll or conf.get("poll") or 3.0), once=args.once,
        **({"name": str(args.name or conf["name"])} if args.name or conf.get("name") else {}),
    )
    if path:
        print(f"testcli: settings from {path}")
    if conf.get("secrets") and not args.no_secrets:
        from .config import run_secrets

        try:
            run_secrets(conf["secrets"], cwd)
        except CliError as e:
            # The agent still starts: tests that need these secrets fail, the others run; reports are served.
            print(f"testcli: WARNING: {e}; starting anyway", file=sys.stderr, flush=True)
    return run_agent(cfg)


def cmd_init(args: argparse.Namespace) -> int:
    from .config import CONFIG_NAMES, env_is_ignored, init_text

    folder = Path(args.cwd or ".").resolve()
    target = folder / CONFIG_NAMES[0]
    if target.exists() and not args.force:
        return _fail(f"{target} already exists (--force to overwrite)")
    url = args.url or os.environ.get("TESTHARBOR_URL", "")
    project = args.project or os.environ.get("TESTHARBOR_PROJECT")
    text = init_text(folder, url, int(project) if project else None, args.framework)
    target.write_text(text, encoding="utf-8")
    print(f"Wrote {target}:\n")
    print(text)
    ignored = env_is_ignored(folder)
    print("Next:")
    print("  1. Put the API token (TestHarbor: API tokens) into .env next to it:  TESTHARBOR_TOKEN=th_...")
    if ignored is False:
        print("     ! .env is NOT ignored by git here: add `.env` to .gitignore before writing the token")
    print("  2. Start the agent here:  testcli agent")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="testcli", description="TestHarbor command-line client")
    parser.add_argument("--version", action="version", version=f"testcli {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    up = sub.add_parser("upload", help="upload JUnit XML report(s) as a test run",
                        description="Upload JUnit XML files or Playwright JSON reports (paths, globs or directories).")
    up.add_argument("files", nargs="+",
                    help="JUnit XML / Playwright JSON files, globs (reports/*.xml) or directories (*.xml inside)")
    up.add_argument("--project", "-p", help="project id (or TESTHARBOR_PROJECT)")
    up.add_argument("--run-name", "-n", help="run name (default: CI name + build number, or a timestamp)")
    up.add_argument("--description", help="run description (markdown)")
    up.add_argument("--branch", help="git branch (auto-detected in CI)")
    up.add_argument("--commit", help="git commit sha (auto-detected in CI)")
    up.add_argument("--build-url", help="link to the CI build (auto-detected in CI)")
    up.add_argument("--report-url",
                    help="where the HTML report of this run is published (or TESTHARBOR_REPORT_URL); "
                         "with a Playwright JSON report every case links to its test in it")
    up.add_argument("--auto-create", action="store_true",
                    help="create cases for tests that match nothing (in Unsorted › Automated)")
    up.add_argument("--run-id", type=int, help="append to an existing open run (e.g. parallel CI shards)")
    up.add_argument("--fail-on-unmatched", action="store_true",
                    help=f"exit with code {EXIT_UNMATCHED} if some tests matched no case")
    up.add_argument("--no-ci-detect", action="store_true", help="don't read CI environment variables")
    up.add_argument("--url", help="TestHarbor base URL (or TESTHARBOR_URL)")
    up.add_argument("--token", help="API token (or TESTHARBOR_TOKEN; prefer the env var)")
    up.add_argument("--json", action="store_true", help="print the raw JSON response")
    up.set_defaults(func=cmd_upload)

    ag = sub.add_parser(
        "agent", help="run tests when someone presses \"Run autotests\" in TestHarbor",
        description="Wait for jobs from TestHarbor, run the tests with --command, upload --report into the "
                    "job's run. The command is only ever taken from here, never from the server.")
    ag.add_argument("--project", "-p", help="project id (or TESTHARBOR_PROJECT)")
    ag.add_argument("--command", "-c", help='how to run the tests (default: testharbor.toml, else "npx playwright test")')
    ag.add_argument("--report", "-r",
                    help="report the command writes: Playwright JSON or JUnit XML (default: reports/results.json); "
                         "may be a glob and contain {job_id}, e.g. 'reports/t{job_id}/*/junit.xml'")
    ag.add_argument("--cwd", help="folder to run the tests in (default: the folder of testharbor.toml, else current)")
    ag.add_argument("--config", help="settings file (default: testharbor.toml / .json here or in a parent folder)")
    ag.add_argument("--select", choices=["grep", "args", "env", "none"],
                    help="how selected tests reach the command: --grep regex, node id arguments, or only the "
                         "TESTHARBOR_SELECTION file")
    ag.add_argument("--report-url",
                    help="where the HTML report is served, e.g. http://localhost:9323/index.html "
                         "(or TESTHARBOR_REPORT_URL; may contain {job_id}); cases link to their test in it")
    ag.add_argument("--auto-create", action="store_true",
                    help="create cases for tests that match nothing (in Unsorted › Automated)")
    ag.add_argument("--grep-arg",
                    help='option used to run only selected cases (default: --grep; "" to append nothing, '
                         'e.g. when the command reads TESTHARBOR_CASE_IDS itself)')
    ag.add_argument("--options",
                    help="JSON file of run options a person may set in TestHarbor (environment, roles, browser…); "
                         "they reach the command as environment variables")
    ag.add_argument("--catalog",
                    help="JSON file listing the tests ({\"tests\": [{key, title, path, steps…}]}), sent when the "
                         "agent starts; synced into cases in TestHarbor after a preview")
    ag.add_argument("--no-secrets", action="store_true",
                    help="don't run the `secrets` commands of testharbor.toml at start (they are still valid)")
    ag.add_argument("--name", help="agent name shown in TestHarbor (default: host name)")
    ag.add_argument("--poll", type=float, help="seconds between checks for new jobs (default 3)")
    ag.add_argument("--once", action="store_true", help="exit after one job")
    ag.add_argument("--url", help="TestHarbor base URL (or TESTHARBOR_URL)")
    ag.add_argument("--token", help="API token (or TESTHARBOR_TOKEN; prefer the env var)")
    srv = ag.add_argument_group(
        "server mode", "Run branches of a git repository in clean checkouts instead of a folder "
                       "(credentials: TESTHARBOR_GIT_TOKEN / TESTHARBOR_GIT_USER, or the machine's SSH key)")
    srv.add_argument("--repo", help="git URL of the tests (or TESTHARBOR_REPO), e.g. "
                                    "https://bitbucket.org/team/qa-tests.git")
    srv.add_argument("--branch", help="default branch (or TESTHARBOR_BRANCH; default: the repository's)")
    srv.add_argument("--repo-path", help="folder of testharbor.toml in the repository (or TESTHARBOR_REPO_PATH; "
                                         "default: found)")
    srv.add_argument("--env-file", help="the tests' .env (passwords), copied into every checkout "
                                        "(or TESTHARBOR_TESTS_ENV)")
    srv.add_argument("--secret-files", help="a folder copied into every checkout as is, e.g. with "
                                            "config/credentials.ini (or TESTHARBOR_SECRET_FILES)")
    srv.add_argument("--workdir", help="where the clone and checkouts live (or TESTHARBOR_WORKDIR; "
                                       "default ~/.cache/testharbor/<repo>)")
    ag.set_defaults(func=cmd_agent)

    ini = sub.add_parser("init", help="write a testharbor.toml for the tests in this folder",
                         description="Detect Playwright or pytest and write testharbor.toml, so `testcli agent` "
                                     "needs no flags.")
    ini.add_argument("--project", "-p", help="TestHarbor project id (or TESTHARBOR_PROJECT)")
    ini.add_argument("--url", help="TestHarbor address (or TESTHARBOR_URL)")
    ini.add_argument("--framework", choices=["playwright", "pytest", "custom"], help="default: detected")
    ini.add_argument("--cwd", help="the tests' folder (default: current)")
    ini.add_argument("--force", action="store_true", help="overwrite an existing testharbor.toml")
    ini.set_defaults(func=cmd_init)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
