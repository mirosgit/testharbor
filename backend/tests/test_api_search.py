"""Case search and filtering."""

import pytest
from httpx import AsyncClient

from tests_helpers import ids


@pytest.fixture
async def data(make):  # type: ignore[no-untyped-def]
    p = await make.project()
    s = await make.suite(p["id"], "Web")
    s2 = await make.suite(p["id"], "API")
    auth = await make.section(s["id"], "Auth")
    login = await make.section(s["id"], "Login", parent_id=auth["id"])
    cart = await make.section(s["id"], "Cart")
    api = await make.section(s2["id"], "Orders")
    await make.case(auth["id"], "Auth overview", tags=["auth"], priority="low")
    await make.case(login["id"], "Login with 100% valid creds", tags=["auth", "smoke"],
                    priority="critical", automation_status="automated")
    await make.case(login["id"], "Login_locked", tags=["auth"], priority="high",
                    automation_status="to_be_automated", type="security")
    await make.case(cart["id"], "Add to cart", tags=["smoke"], priority="high")
    await make.case(api["id"], "Create order", tags=["api"], automation_status="automated")
    return {"p": p, "s": s, "s2": s2, "auth": auth, "login": login}


async def _titles(client: AsyncClient, pid: int, **params) -> list[str]:  # type: ignore[no-untyped-def]
    r = await client.get(f"/api/projects/{pid}/cases", params=params)
    assert r.status_code == 200, r.text
    return sorted(ids(r.json(), "title"))


async def test_filters(client: AsyncClient, data) -> None:  # type: ignore[no-untyped-def]
    pid = data["p"]["id"]
    assert len(await _titles(client, pid)) == 5
    assert len(await _titles(client, pid, suite_id=data["s"]["id"])) == 4
    # Section includes subsections by default.
    assert await _titles(client, pid, section_id=data["auth"]["id"]) == [
        "Auth overview", "Login with 100% valid creds", "Login_locked"
    ]
    assert await _titles(client, pid, section_id=data["auth"]["id"], include_subsections=False) == [
        "Auth overview"
    ]
    # Title search is case-insensitive; LIKE wildcards are literal.
    assert await _titles(client, pid, q="LOGIN") == ["Login with 100% valid creds", "Login_locked"]
    assert await _titles(client, pid, q="100%") == ["Login with 100% valid creds"]
    assert await _titles(client, pid, q="n_l") == ["Login_locked"]
    # Tags: must have all.
    assert await _titles(client, pid, tags=["auth", "smoke"]) == ["Login with 100% valid creds"]
    assert await _titles(client, pid, tags="AUTH,smoke") == ["Login with 100% valid creds"]
    # Multi-value enums: any of.
    assert await _titles(client, pid, priority=["high", "critical"]) == [
        "Add to cart", "Login with 100% valid creds", "Login_locked"
    ]
    assert await _titles(client, pid, automation_status="automated", suite_id=data["s"]["id"]) == [
        "Login with 100% valid creds"
    ]
    assert await _titles(client, pid, type="security") == ["Login_locked"]


async def test_search_by_case_id(client: AsyncClient, data, make) -> None:  # type: ignore[no-untyped-def]
    pid = data["p"]["id"]
    c = await make.case(data["auth"]["id"], "Something unrelated")
    assert await _titles(client, pid, q=f"C{c['id']}") == ["Something unrelated"]


async def test_invalid_filter_value(client: AsyncClient, data) -> None:  # type: ignore[no-untyped-def]
    r = await client.get(f"/api/projects/{data['p']['id']}/cases", params={"priority": "urgent"})
    assert r.status_code == 422


async def test_pagination_and_total(client: AsyncClient, data) -> None:  # type: ignore[no-untyped-def]
    r = await client.get(f"/api/projects/{data['p']['id']}/cases", params={"limit": 2, "offset": 2})
    body = r.json()
    assert body["total"] == 5 and len(body["items"]) == 2


async def test_tags_endpoint(client: AsyncClient, data) -> None:  # type: ignore[no-untyped-def]
    r = await client.get(f"/api/projects/{data['p']['id']}/tags")
    assert r.json() == ["api", "auth", "smoke"]


async def test_case_list_sorting_within_sections_and_paging(client, make) -> None:  # type: ignore[no-untyped-def]
    p = await make.project()
    s = await make.suite(p["id"])
    first = await make.section(s["id"], "First")
    second = await make.section(s["id"], "Second")
    child = await make.section(s["id"], "Child", parent_id=first["id"])  # tree: First, Child, Second
    a = await make.case(second["id"], "b-case", priority="low", sprint="Sprint 10")
    b = await make.case(first["id"], "Zeta", priority="critical", sprint="Sprint 9")
    c = await make.case(first["id"], "alpha", priority="high")
    d = await make.case(child["id"], "Mid", priority="medium", sprint="Sprint 2")

    async def keys(**params):  # type: ignore[no-untyped-def]
        r = await client.get(f"/api/projects/{p['id']}/cases", params={"suite_id": s["id"], **params})
        assert r.status_code == 200, r.text
        return [x["id"] for x in r.json()["items"]]

    # Manual = drag-and-drop order inside each section; sections in tree order.
    assert await keys() == [b["id"], c["id"], d["id"], a["id"]]
    assert await keys(sort="title") == [c["id"], b["id"], d["id"], a["id"]]
    assert await keys(sort="priority", order="desc") == [b["id"], c["id"], d["id"], a["id"]]
    assert await keys(sort="priority") == [c["id"], b["id"], d["id"], a["id"]]
    # Natural sprint order, empty values last.
    await client.patch(f"/api/cases/{c['id']}", json={"sprint": "Sprint 10"})
    assert await keys(sort="sprint") == [b["id"], c["id"], d["id"], a["id"]]
    await client.patch(f"/api/cases/{b['id']}", json={"sprint": None})
    assert await keys(sort="sprint") == [c["id"], b["id"], d["id"], a["id"]]
    # Paging keeps the same order.
    r = (await client.get(f"/api/projects/{p['id']}/cases",
                          params={"suite_id": s["id"], "limit": 2, "offset": 2})).json()
    assert r["total"] == 4 and [x["id"] for x in r["items"]] == [d["id"], a["id"]]
    assert (await client.get(f"/api/projects/{p['id']}/cases", params={"sort": "nope"})).status_code == 422


async def test_runs_sorting(client, make) -> None:  # type: ignore[no-untyped-def]
    p, s, sec = await make.tree()
    await make.case(sec["id"])
    ids = []
    for name in ("beta", "Alpha", "gamma"):
        r = await client.post(f"/api/projects/{p['id']}/runs", json={"name": name, "suite_id": s["id"]})
        ids.append(r.json()["id"])

    async def names(**params):  # type: ignore[no-untyped-def]
        r = await client.get(f"/api/projects/{p['id']}/runs", params=params)
        assert r.status_code == 200, r.text
        return [x["name"] for x in r.json()["items"]]

    assert await names() == ["gamma", "Alpha", "beta"]  # newest first
    assert await names(order="asc") == ["beta", "Alpha", "gamma"]
    assert await names(sort="name", order="asc") == ["Alpha", "beta", "gamma"]
