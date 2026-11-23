"""The MCP endpoint (/api/mcp): an API token is required, tools read and write as the token's owner."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient

from app.mcp_server import server
from tests.conftest import Factory, _client

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
async def mcp_running() -> AsyncIterator[None]:
    """The app's lifespan starts this in production. It runs once per process, entered and left in one task."""
    stop = asyncio.Event()

    async def run() -> None:
        async with server.session_manager.run():
            await stop.wait()

    task = asyncio.create_task(run())
    await asyncio.sleep(0)
    yield
    stop.set()
    await task


class MCP:
    def __init__(self, c: AsyncClient, token: str) -> None:
        self.c, self.token, self.n = c, token, 0

    async def rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.n += 1
        r = await self.c.post(
            "/api/mcp",
            headers={**HEADERS, "Authorization": f"Bearer {self.token}"},
            json={"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}},
        )
        assert r.status_code == 200, r.text
        return r.json()

    async def call(self, tool: str, **args: Any) -> Any:
        out = (await self.rpc("tools/call", {"name": tool, "arguments": args}))["result"]
        assert not out.get("isError"), out
        return out["structuredContent"]

    async def error(self, tool: str, **args: Any) -> str:
        out = (await self.rpc("tools/call", {"name": tool, "arguments": args}))["result"]
        assert out.get("isError"), out
        return out["content"][0]["text"]


@pytest.fixture
async def mcp(tester: AsyncClient, mcp_running: None) -> AsyncIterator[MCP]:
    token = (await tester.post("/api/tokens", json={"name": "claude"})).json()["token"]
    async with _client() as c:
        m = MCP(c, token)
        init = await m.rpc("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"},
        })
        assert init["result"]["serverInfo"]["name"] == "TestHarbor"
        yield m


async def test_needs_a_token(anon: AsyncClient, mcp_running: None) -> None:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    r = await anon.post("/api/mcp", headers=HEADERS, json=body)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    r = await anon.post("/api/mcp", headers={**HEADERS, "Authorization": "Bearer th_wrong"}, json=body)
    assert r.status_code == 401


async def test_tools_are_listed_and_none_delete(mcp: MCP) -> None:
    tools = {t["name"]: t for t in (await mcp.rpc("tools/list"))["result"]["tools"]}
    assert {"list_projects", "get_project_structure", "search_cases", "get_case", "get_run",
            "create_case", "update_case", "create_section"} <= set(tools)
    assert not [n for n in tools if "delete" in n or "remove" in n]
    assert tools["search_cases"]["annotations"]["readOnlyHint"] is True
    assert tools["create_case"]["annotations"]["readOnlyHint"] is False


async def test_read_and_write_cases_as_the_token_owner(mcp: MCP, client: AsyncClient) -> None:
    make = Factory(client)
    p, s, sec = await make.tree()
    await make.case(sec["id"], "Login with a valid password", tags=["auth"])
    await make.case(sec["id"], "Export orders")

    assert [x["name"] for x in (await mcp.call("list_projects"))["projects"]] == ["P"]
    structure = await mcp.call("get_project_structure", project_id=p["id"])
    assert structure["suites"][0]["sections"][0]["id"] == sec["id"]

    found = await mcp.call("search_cases", project_id=p["id"], query="login")
    assert found["total"] == 1 and found["cases"][0]["title"] == "Login with a valid password"

    sub = await mcp.call("create_section", suite_id=s["id"], name="Password reset", parent_id=sec["id"])
    made = await mcp.call(
        "create_case", section_id=sub["id"], title="Reset link expires after an hour", priority="high",
        steps=[{"action": "Open a reset link older than an hour", "expected": "The link is refused"}],
    )
    # New cases wait for a person to review them, and carry the token owner's name.
    case = await mcp.call("get_case", case=made["key"])
    assert case["state"] == "pending_review"
    assert case["updated_by"] == "Tom Tester"
    assert case["steps"] == [{"action": "Open a reset link older than an hour", "expected": "The link is refused"}]

    changed = await mcp.call("update_case", case=made["key"], state="active", tags=["auth", "email"])
    assert changed["state"] == "active" and changed["tags"] == ["auth", "email"]
    assert (await mcp.call("get_case", case=made["key"]))["priority"] == "high"  # left alone

    # API errors come back as tool errors the agent can read.
    assert "404" in await mcp.error("get_case", case="C999999")
    assert "Nothing to change" in await mcp.error("update_case", case=made["key"])


async def test_runs(mcp: MCP, client: AsyncClient) -> None:
    make = Factory(client)
    p, _, sec = await make.tree()
    c1 = await make.case(sec["id"], "Passes")
    c2 = await make.case(sec["id"], "Fails")
    run = (await client.post(f"/api/projects/{p['id']}/runs",
                             json={"name": "Nightly", "case_ids": [c1["id"], c2["id"]]})).json()
    await client.post(f"/api/runs/{run['id']}/results", json={"case_id": c1["id"], "status": "passed"})
    await client.post(f"/api/runs/{run['id']}/results",
                      json={"case_id": c2["id"], "status": "failed", "error_message": "Timeout"})

    assert [r["name"] for r in (await mcp.call("list_runs", project_id=p["id"]))["runs"]] == ["Nightly"]
    failed = await mcp.call("get_run", run_id=run["id"], status=["failed"])
    assert failed["cases"] == [{"key": c2["key"], "title": "Fails", "section": "Sec", "status": "failed",
                                "error": "Timeout"}]
