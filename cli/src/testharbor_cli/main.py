"""testcli: upload JUnit XML results to TestHarbor.

    export TESTHARBOR_URL=https://testharbor.example.com
    export TESTHARBOR_TOKEN=th_...
    testcli upload junit.xml --project 1 --run-name "Nightly #123" --branch main --commit abc123
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
