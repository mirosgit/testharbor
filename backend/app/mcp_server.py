"""MCP server: lets an AI agent (Claude Code, Claude Desktop, …) read TestHarbor and write test cases.

Served at /api/mcp (Streamable HTTP, stateless, JSON responses). The agent runs on the person's side, on
their own Claude account; TestHarbor holds no AI credentials. It authenticates with a TestHarbor API
token (`Authorization: Bearer th_…`) and acts as that token's owner.

Every tool is a thin wrapper over the REST API, called in-process with the caller's token, so the same
permissions, validation and audit fields (`updated_by`) apply as for any other client. There are no
tools that delete anything.
"""

import contextvars
from typing import Annotated, Any

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.auth import _token_principal
from app.db import SessionLocal
from app.models import AutomationStatus, CaseState, CaseType, Priority, ResultStatus

PATH = "/api/mcp"

# The caller's bearer token, for the in-process REST calls of the current request.
_token: contextvars.ContextVar[str] = contextvars.ContextVar("mcp_token")

INSTRUCTIONS = """\
TestHarbor is a test case management tool: Project > Suite > Section tree > Test case (C142).
Runs hold the results of executing cases (passed, failed, blocked, retest, skipped, untested).

- Find things with list_projects, get_project_structure and search_cases before writing.
- Write new cases into an existing section that fits (get_project_structure shows the tree);
  create a section only when none fits.
- New cases start as Pending review, so a person checks them before they count.
- Use the project's own roles, owners, sprints and tags (get_project_values) instead of inventing new ones.
- Steps are short actions, each with the result to expect. Don't state behaviour you weren't told about.
"""

server = MCPServer("TestHarbor", instructions=INSTRUCTIONS)
READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)


async def _api(method: str, path: str, **kwargs: Any) -> Any:
    """Call the REST API in-process as the caller."""
    from app.main import app  # imported late: app.main imports this module

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testharbor",
        headers={"Authorization": f"Bearer {_token.get()}"},
        timeout=60,
    ) as client:
        r = await client.request(method, f"/api{path}", **kwargs)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        raise ToolError(f"{r.status_code}: {detail}")
    return r.json() if r.content else None


def _case_brief(c: dict[str, Any]) -> dict[str, Any]:
    return {k: c[k] for k in ("key", "title", "section_id", "state", "priority", "type", "automation_status", "tags")}


def _drop_empty(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


# --- Reading -----------------------------------------------------------------------------


@server.tool(annotations=READ)
async def list_projects() -> dict[str, Any]:
    """The projects, with their ids and how many suites, cases and runs each has."""
    return {"projects": [
        {k: p[k] for k in ("id", "name", "description", "suite_count", "case_count", "run_count")}
        for p in await _api("GET", "/projects")
    ]}


@server.tool(annotations=READ)
async def get_project_structure(project_id: int) -> dict[str, Any]:
    """The project's suites, each with its section tree (ids, names, parent ids, direct case counts)."""
    suites = await _api("GET", f"/projects/{project_id}/suites")
    out = []
    for s in suites:
        sections = await _api("GET", f"/suites/{s['id']}/sections")
        out.append({
            "suite_id": s["id"],
            "name": s["name"],
            "description": s["description"],
            "case_count": s["case_count"],
            "sections": [
                {k: x[k] for k in ("id", "parent_id", "name", "description", "case_count")} for x in sections
            ],
        })
    return {"suites": out}


@server.tool(annotations=READ)
async def get_project_values(project_id: int) -> dict[str, Any]:
    """Values already used in the project: roles, owners, sprints, tags and custom fields. Reuse them."""
    values = await _api("GET", f"/projects/{project_id}/case-values")
    return {
        **values,
        "tags": await _api("GET", f"/projects/{project_id}/tags"),
        "custom_fields": await _api("GET", f"/projects/{project_id}/custom-fields"),
    }


@server.tool(annotations=READ)
async def search_cases(
    project_id: int,
    query: Annotated[str | None, Field(description="Words in the title, or a case id like C142")] = None,
    suite_id: int | None = None,
    section_id: Annotated[int | None, Field(description="This section and its subsections")] = None,
    state: list[CaseState] | None = None,
    priority: list[Priority] | None = None,
    automation_status: list[AutomationStatus] | None = None,
    tags: Annotated[list[str] | None, Field(description="Cases must have all of these")] = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict[str, Any]:
    """Find test cases. Returns a short form of each; use get_case for steps and all fields."""
    params: dict[str, Any] = _drop_empty({
        "q": query, "suite_id": suite_id, "section_id": section_id, "state": state, "priority": priority,
        "automation_status": automation_status, "tags": tags, "limit": limit, "offset": offset,
    })
    found = await _api("GET", f"/projects/{project_id}/cases", params=params)
    return {"total": found["total"], "cases": [_case_brief(c) for c in found["items"]]}


@server.tool(annotations=READ)
async def get_case(case: Annotated[str, Field(description="Case id, like C142 or 142")]) -> dict[str, Any]:
    """One test case with all its fields and steps."""
    c = await _api("GET", f"/cases/{case}")
    return _drop_empty({k: v for k, v in c.items() if k not in ("position", "project_id")})


@server.tool(annotations=READ)
async def get_case_history(case: Annotated[str, Field(description="Case id, like C142")]) -> dict[str, Any]:
    """The case's results across runs, newest first."""
    return {"results": await _api("GET", f"/cases/{case}/history")}


@server.tool(annotations=READ)
async def list_runs(project_id: int, limit: Annotated[int, Field(ge=1, le=100)] = 20) -> dict[str, Any]:
    """The newest test runs of the project with their status counts."""
    runs = await _api("GET", f"/projects/{project_id}/runs", params={"limit": limit})
    return {"total": runs["total"], "runs": [
        _drop_empty({k: r[k] for k in ("id", "name", "source", "branch", "closed", "created_at", "created_by_name", "stats")})
        for r in runs["items"]
    ]}


@server.tool(annotations=READ)
async def get_run(
    run_id: int,
    status: Annotated[
        list[ResultStatus] | None,
        Field(description="Only cases with these statuses, for example ['failed']"),
    ] = None,
) -> dict[str, Any]:
    """A run and its cases with their current status and latest result (error message included)."""
    run = await _api("GET", f"/runs/{run_id}")
    cases = await _api("GET", f"/runs/{run_id}/cases", params={"status": status} if status else None)
    return {
        "run": _drop_empty(run),
        "cases": [
            _drop_empty({
                "key": c["key"], "title": c["title"], "section": c["section_path"], "status": c["status"],
                "error": (c["last_result"] or {}).get("error_message"),
                "comment": (c["last_result"] or {}).get("comment"),
                "config": (c["last_result"] or {}).get("config"),
            })
            for c in cases
        ],
    }


@server.tool(annotations=READ)
async def get_dashboard(project_id: int, days: Annotated[int, Field(ge=1, le=365)] = 30) -> dict[str, Any]:
    """The project's numbers: coverage, case mix, pass rate, failing and flaky cases, recent runs."""
    return await _api("GET", f"/projects/{project_id}/dashboard", params={"days": days})


# --- Writing -----------------------------------------------------------------------------


class Step(BaseModel):
    action: str = Field(description="What the tester does")
    expected: str = Field(default="", description="What should happen")


class CustomField(BaseModel):
    name: str
    value: str


@server.tool(annotations=WRITE)
async def create_section(
    suite_id: int,
    name: str,
    parent_id: Annotated[int | None, Field(description="Parent section; none for the top level")] = None,
    description: str = "",
) -> dict[str, Any]:
    """Add a section to a suite (only when no existing section fits)."""
    s = await _api("POST", f"/suites/{suite_id}/sections",
                   json={"name": name, "parent_id": parent_id, "description": description})
    return {k: s[k] for k in ("id", "suite_id", "parent_id", "name")}


@server.tool(annotations=WRITE)
async def create_case(
    section_id: int,
    title: str,
    steps: list[Step] | None = None,
    preconditions: str = "",
    description: str = "",
    expected_result: Annotated[str, Field(description="The overall result, when the steps don't carry it")] = "",
    priority: Priority = Priority.medium,
    type: CaseType = CaseType.functional,
    tags: list[str] | None = None,
    roles: Annotated[list[str] | None, Field(description="Applicable roles, from get_project_values")] = None,
    owner: str | None = None,
    sprint: str | None = None,
    custom_fields: list[CustomField] | None = None,
    state: Annotated[CaseState, Field(description="Leave as pending_review unless told otherwise")] = CaseState.pending_review,
) -> dict[str, Any]:
    """Create a test case. It starts as Pending review, for a person to check."""
    body = {
        "section_id": section_id, "title": title, "description": description, "preconditions": preconditions,
        "steps": [s.model_dump() for s in steps or []], "expected_result": expected_result,
        "priority": priority, "type": type, "tags": tags or [], "roles": roles or [], "owner": owner,
        "sprint": sprint, "custom_fields": [f.model_dump() for f in custom_fields or []], "state": state,
    }
    return _case_brief(await _api("POST", "/cases", json=body))


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True,
                                         open_world_hint=False))
async def update_case(
    case: Annotated[str, Field(description="Case id, like C142")],
    title: str | None = None,
    steps: Annotated[list[Step] | None, Field(description="Replaces all steps")] = None,
    preconditions: str | None = None,
    description: str | None = None,
    expected_result: str | None = None,
    priority: Priority | None = None,
    tags: Annotated[list[str] | None, Field(description="Replaces all tags")] = None,
    roles: Annotated[list[str] | None, Field(description="Replaces all roles")] = None,
    owner: str | None = None,
    sprint: str | None = None,
    state: CaseState | None = None,
    section_id: Annotated[int | None, Field(description="Move the case to this section")] = None,
) -> dict[str, Any]:
    """Change fields of a test case; fields left out stay as they are. Read it with get_case first."""
    patch = {
        "title": title, "preconditions": preconditions, "description": description,
        "expected_result": expected_result, "priority": priority, "tags": tags, "roles": roles,
        "owner": owner, "sprint": sprint, "state": state, "section_id": section_id,
        "steps": [s.model_dump() for s in steps] if steps is not None else None,
    }
    patch = {k: v for k, v in patch.items() if v is not None}
    if not patch:
        raise ToolError("Nothing to change: pass at least one field")
    return _case_brief(await _api("PATCH", f"/cases/{case}", json=patch))


# --- HTTP --------------------------------------------------------------------------------

# Bearer tokens, not cookies, so DNS-rebinding protection (meant for servers on localhost) is off.
_mcp_app = server.streamable_http_app(
    streamable_http_path=PATH,
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


class _MCPEndpoint:
    """The MCP app behind a TestHarbor API token check (an ASGI app, so Starlette routes to it as is)."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope)
        async with SessionLocal() as session:
            principal = await _token_principal(request, session)
        if principal is None:
            response = JSONResponse(
                {"error": "Send a TestHarbor API token: Authorization: Bearer th_… (Settings › API tokens)"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            return await response(scope, receive, send)
        reset = _token.set(request.headers["authorization"].partition(" ")[2].strip())
        try:
            await _mcp_app(scope, receive, send)
        finally:
            _token.reset(reset)


mcp_asgi: ASGIApp = _MCPEndpoint()
