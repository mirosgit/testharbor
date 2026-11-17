"""Auth, projects, suites, sections, cases."""

from httpx import AsyncClient

from tests_helpers import ids

# --- Auth ----------------------------------------------------------------------------


async def test_requires_auth(anon: AsyncClient) -> None:
    assert (await anon.get("/api/projects")).status_code == 401
    assert (await anon.get("/api/health")).status_code == 200


async def test_tampered_cookie_rejected(anon: AsyncClient) -> None:
    anon.cookies.set("th_session", "eyJ1IjoiYWRtaW4ifQ.forged.sig")
    assert (await anon.get("/api/projects")).status_code == 401


# --- Projects / suites ---------------------------------------------------------------


async def test_project_crud_with_counts(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p = await make.project("Shop", description="desc")
    assert p["suite_count"] == 0
    s = await make.suite(p["id"])
    sec = await make.section(s["id"])
    await make.case(sec["id"])

    got = (await client.get(f"/api/projects/{p['id']}")).json()
    assert (got["suite_count"], got["case_count"], got["run_count"]) == (1, 1, 0)

    r = await client.patch(f"/api/projects/{p['id']}", json={"name": "Shop 2"})
    assert r.json()["name"] == "Shop 2" and r.json()["description"] == "desc"
    assert [x["name"] for x in (await client.get("/api/projects")).json()] == ["Shop 2"]

    assert (await client.delete(f"/api/projects/{p['id']}")).status_code == 204
    assert (await client.get(f"/api/projects/{p['id']}")).status_code == 404
    assert (await client.get(f"/api/suites/{s['id']}")).status_code == 404


async def test_project_validation(client: AsyncClient) -> None:
    assert (await client.post("/api/projects", json={"name": ""})).status_code == 422
    assert (await client.get("/api/projects/999")).status_code == 404


async def test_suite_crud(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p = await make.project()
    a = await make.suite(p["id"], "B suite")
    await make.suite(p["id"], "A suite")
    names = [s["name"] for s in (await client.get(f"/api/projects/{p['id']}/suites")).json()]
    assert names == ["A suite", "B suite"]
    r = await client.patch(f"/api/suites/{a['id']}", json={"description": "x"})
    assert r.json()["description"] == "x"
    assert (await client.delete(f"/api/suites/{a['id']}")).status_code == 204


# --- Sections ------------------------------------------------------------------------


async def test_section_tree_and_moves(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p = await make.project()
    s = await make.suite(p["id"])
    a = await make.section(s["id"], "A")
    b = await make.section(s["id"], "B")
    a1 = await make.section(s["id"], "A1", parent_id=a["id"])
    assert (a["position"], b["position"], a1["position"]) == (0, 1, 0)

    # Move B under A, first position.
    r = await client.patch(f"/api/sections/{b['id']}", json={"parent_id": a["id"], "position": 0})
    assert r.status_code == 200
    secs = {x["name"]: x for x in (await client.get(f"/api/suites/{s['id']}/sections")).json()}
    assert secs["B"]["parent_id"] == a["id"]
    assert (secs["B"]["position"], secs["A1"]["position"]) == (0, 1)

    # Back to top level (explicit null).
    r = await client.patch(f"/api/sections/{b['id']}", json={"parent_id": None})
    assert r.json()["parent_id"] is None

    # Cycles are rejected.
    r = await client.patch(f"/api/sections/{a['id']}", json={"parent_id": a1["id"]})
    assert r.status_code == 400
    r = await client.patch(f"/api/sections/{a['id']}", json={"parent_id": a["id"]})
    assert r.status_code == 400


async def test_section_parent_must_be_in_same_suite(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p = await make.project()
    s1, s2 = await make.suite(p["id"]), await make.suite(p["id"])
    other = await make.section(s2["id"])
    r = await client.post(f"/api/suites/{s1['id']}/sections", json={"name": "x", "parent_id": other["id"]})
    assert r.status_code == 400


async def test_delete_section_deletes_subtree(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p = await make.project()
    s = await make.suite(p["id"])
    a = await make.section(s["id"], "A")
    a1 = await make.section(s["id"], "A1", parent_id=a["id"])
    c = await make.case(a1["id"])
    assert (await client.delete(f"/api/sections/{a['id']}")).status_code == 204
    assert (await client.get(f"/api/suites/{s['id']}/sections")).json() == []
    assert (await client.get(f"/api/cases/{c['id']}")).status_code == 404


# --- Cases ---------------------------------------------------------------------------


async def test_case_crud(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p, s, sec = await make.tree()
    c = await make.case(
        sec["id"],
        "Login works",
        steps=[{"action": "Open /login", "expected": "Form shown"}, {"action": "Submit"}],
        tags=[" Auth ", "smoke", "auth", ""],
        priority="high",
        automation_key="  tests/test_auth.py::test_login ",
    )
    assert c["key"] == f"C{c['id']}"
    assert (c["project_id"], c["suite_id"]) == (p["id"], s["id"])
    assert c["tags"] == ["auth", "smoke"]
    assert c["automation_key"] == "tests/test_auth.py::test_login"
    assert c["steps"][1] == {"action": "Submit", "expected": ""}

    # Lookup by "C<id>" and by plain id.
    assert (await client.get(f"/api/cases/C{c['id']}")).json()["title"] == "Login works"
    assert (await client.get(f"/api/cases/c{c['id']}")).status_code == 200
    assert (await client.get("/api/cases/X1")).status_code == 422

    r = await client.patch(f"/api/cases/C{c['id']}", json={"title": "Login", "automation_key": None})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Login" and body["automation_key"] is None
    assert body["priority"] == "high"  # untouched

    assert (await client.delete(f"/api/cases/{c['id']}")).status_code == 204
    assert (await client.get(f"/api/cases/{c['id']}")).status_code == 404


async def test_case_validation(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    _, _, sec = await make.tree()
    for bad in ({"title": ""}, {"title": "x", "priority": "urgent"}, {"title": "x", "type": "nope"}):
        r = await client.post("/api/cases", json={"section_id": sec["id"], **bad})
        assert r.status_code == 422, bad
    r = await client.post("/api/cases", json={"section_id": 999, "title": "x"})
    assert r.status_code == 404


async def test_automation_key_conflict_is_409(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    _, _, sec = await make.tree()
    await make.case(sec["id"], automation_key="k")
    r = await client.post("/api/cases", json={"section_id": sec["id"], "title": "x", "automation_key": "k"})
    assert r.status_code == 409
    # Same key in another project is fine.
    _, _, sec2 = await make.tree()
    await make.case(sec2["id"], automation_key="k")


async def test_case_positions_and_move(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p = await make.project()
    s1, s2 = await make.suite(p["id"]), await make.suite(p["id"])
    a = await make.section(s1["id"], "A")
    b = await make.section(s2["id"], "B")
    c1, c2, c3 = [await make.case(a["id"], t) for t in ("1", "2", "3")]
    d1 = await make.case(b["id"], "d1")
    assert [c["position"] for c in (c1, c2, c3)] == [0, 1, 2]

    # Move c3 and c1 into B at index 0 (cross-suite within the project).
    r = await client.post(
        "/api/cases/move", json={"case_ids": [c3["id"], c1["id"]], "section_id": b["id"], "position": 0}
    )
    assert r.status_code == 200
    listed = (await client.get(f"/api/projects/{p['id']}/cases", params={"section_id": b["id"]})).json()
    assert [(c["title"], c["position"], c["suite_id"]) for c in listed["items"]] == [
        ("3", 0, s2["id"]), ("1", 1, s2["id"]), ("d1", 2, s2["id"])
    ]
    # Reorder within the same section.
    await client.post("/api/cases/move", json={"case_ids": [d1["id"]], "section_id": b["id"], "position": 0})
    listed = (await client.get(f"/api/projects/{p['id']}/cases", params={"section_id": b["id"]})).json()
    assert ids(listed, "title") == ["d1", "3", "1"]

    # PATCH section_id also moves (to the end).
    r = await client.patch(f"/api/cases/{c2['id']}", json={"section_id": b["id"]})
    assert (r.json()["section_id"], r.json()["position"], r.json()["suite_id"]) == (b["id"], 3, s2["id"])


async def test_cannot_move_case_to_other_project(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    _, _, sec = await make.tree()
    _, _, other = await make.tree()
    c = await make.case(sec["id"])
    r = await client.post("/api/cases/move", json={"case_ids": [c["id"]], "section_id": other["id"]})
    assert r.status_code == 400
    r = await client.post("/api/cases/move", json={"case_ids": [999], "section_id": other["id"]})
    assert r.status_code == 404
