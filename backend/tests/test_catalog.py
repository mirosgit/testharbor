"""Syncing the automated tests' catalog into cases."""

from httpx import AsyncClient

from app.catalog import similarity


def _test(key: str, title: str, **kw):  # type: ignore[no-untyped-def]
    return {
        "key": key,
        "title": title,
        "path": kw.pop("path", ["Checkout", "Discount codes"]),
        "description": "Adds a discount code.",
        "preconditions": "- Given an order exists",
        "steps": [{"action": "When I add a discount code\nAnd I save it", "expected": "Then the message \"Discount Applied\" is shown"}],
        "roles": ["Super Admin", "Admin"],
        "tags": ["regression"],
        **kw,
    }


async def _upload(client: AsyncClient, pid: int, tests: list[dict]):  # type: ignore[no-untyped-def, type-arg]
    r = await client.put(f"/api/projects/{pid}/automation/catalog", json={"agent": "qa-box", "tests": tests})
    assert r.status_code == 200, r.text
    return r.json()


async def _apply(client: AsyncClient, pid: int, preview: dict, **body):  # type: ignore[no-untyped-def, type-arg]
    return await client.post(f"/api/projects/{pid}/automation/catalog/apply",
                             json={"uploaded_at": preview["uploaded_at"], **body})


def test_similarity() -> None:
    assert similarity("A discount code is added to an order", "Discount codes can be added") > 0.45
    assert similarity("A discount code is added to an order", "Order export to CSV") < 0.2
    assert similarity("", "x") == 0


async def test_sync_creates_links_updates_and_outdates(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p, s, sec = await make.tree()
    pid = p["id"]
    await client.patch(f"/api/projects/{pid}", json={"roles": ["Super Admin (SA)"]})
    manual = await make.case(sec["id"], "Discount codes can be added", steps=[{"action": "x", "expected": "y"}])
    tagged = await make.case(sec["id"], "Remove a discount code")
    assert (await client.get(f"/api/projects/{pid}/automation/catalog")).status_code == 404

    tests = [
        _test("t.py::test_add", "A discount code is added to an order"),
        _test("t.py::test_delete", "An expired discount code is removed", case_ids=[tagged["id"]]),
        _test("t.py::test_filter", "Orders are filtered by customer", path=["Checkout", "Filters"], tags=["smoke"]),
    ]
    preview = await _upload(client, pid, tests)
    assert preview["counts"] == {"create": 2, "link": 1, "update": 0, "outdated": 0, "unchanged": 0}
    items = {i["key"]: i for i in preview["items"]}
    assert items["t.py::test_delete"]["case_key"] == tagged["key"]
    # The manual case with a similar title is suggested for the new test.
    assert items["t.py::test_add"]["suggestions"][0]["key"] == manual["key"]
    assert items["t.py::test_add"]["suggestions"][0]["path"].endswith(sec["name"])

    # Nothing changed by uploading or previewing.
    assert (await client.get(f"/api/cases/{tagged['id']}")).json()["automation_key"] is None

    r = await _apply(client, pid, preview, links={"t.py::test_add": manual["id"]})
    assert r.status_code == 200, r.text
    assert r.json() == {"created": 1, "updated": 0, "linked": 2, "outdated": 0, "skipped": 0}

    # Linked manual cases keep their content, get the key.
    m = (await client.get(f"/api/cases/{manual['id']}")).json()
    assert (m["title"], m["automation_key"], m["automation_status"]) == (
        "Discount codes can be added", "t.py::test_add", "automated")
    assert m["steps"] == [{"action": "x", "expected": "y"}]
    # The new case is filled from the test, in Autotests > Checkout > Filters.
    suites = (await client.get(f"/api/projects/{pid}/suites")).json()
    auto = next(x for x in suites if x["name"] == "Autotests")
    cases = (await client.get(f"/api/projects/{pid}/cases", params={"suite_id": auto["id"]})).json()
    items_ = cases["items"] if isinstance(cases, dict) else cases
    (new,) = items_
    full = (await client.get(f"/api/cases/{new['id']}")).json()
    assert full["title"] == "Orders are filtered by customer"
    assert (full["type"], full["automation_status"], full["automation_key"]) == ("smoke", "automated", "t.py::test_filter")
    assert full["roles"] == ["Super Admin (SA)", "Admin"]  # the project's spelling
    assert full["preconditions"] == "- Given an order exists" and full["steps"][0]["action"] == "When I add a discount code  \nAnd I save it"
    sections = (await client.get(f"/api/suites/{auto['id']}/sections")).json()
    by_id = {x["id"]: x for x in sections}
    leaf = by_id[full["section_id"]]
    assert leaf["name"] == "Filters" and by_id[leaf["parent_id"]]["name"] == "Checkout"

    # Second sync: everything unchanged.
    again = await _upload(client, pid, tests)
    assert again["counts"]["unchanged"] == 3 and again["counts"]["create"] == 0

    # The filter test changes, the delete test goes away (its manual case is left alone),
    # and the catalog case of a removed test becomes Outdated.
    tests2 = [tests[0], {**tests[2], "title": "Orders are filtered by customer and status"}]
    p2 = await _upload(client, pid, tests2)
    assert p2["counts"] == {"create": 0, "link": 0, "update": 1, "outdated": 0, "unchanged": 1}
    assert next(i for i in p2["items"] if i["action"] == "update")["changes"] == ["title"]
    assert (await _apply(client, pid, p2)).json()["updated"] == 1
    p3 = await _upload(client, pid, [tests[0]])
    assert p3["counts"]["outdated"] == 1
    assert (await _apply(client, pid, p3)).json()["outdated"] == 1
    assert (await client.get(f"/api/cases/{new['id']}")).json()["state"] == "outdated"
    # It comes back: active again.
    p4 = await _upload(client, pid, tests2)
    assert (await _apply(client, pid, p4)).json()["updated"] == 1
    assert (await client.get(f"/api/cases/{new['id']}")).json()["state"] == "active"


async def test_apply_rules(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p, s, sec = await make.tree()
    pid = p["id"]
    a = await make.case(sec["id"], "A")
    preview = await _upload(client, pid, [_test("k1", "One"), _test("k2", "Two")])
    # A newer catalog makes the preview stale.
    newer = await _upload(client, pid, [_test("k1", "One"), _test("k2", "Two")])
    assert (await _apply(client, pid, preview)).status_code == 409
    bad = await _apply(client, pid, newer, links={"k1": a["id"], "k2": a["id"]})
    assert bad.status_code == 422 and "same case" in bad.text
    assert (await _apply(client, pid, newer, links={"k1": 999999})).status_code == 422
    r = await _apply(client, pid, newer, skip=["k2"])
    assert r.json() == {"created": 1, "updated": 0, "linked": 0, "outdated": 0, "skipped": 1}
    # A catalog case can't be the target of a link.
    created = next(i for i in (await _upload(client, pid, [_test("k1", "One"), _test("k3", "Three")]))["items"]
                   if i["key"] == "k1")
    latest = (await client.get(f"/api/projects/{pid}/automation/catalog")).json()
    r = await _apply(client, pid, latest, links={"k3": created["case_id"]})
    assert r.status_code == 422 and "created from the catalog" in r.text

    dup = await client.put(f"/api/projects/{pid}/automation/catalog",
                           json={"tests": [_test("k1", "One"), _test("k1", "Again")]})
    assert dup.status_code == 422


async def test_claim_carries_automation_keys(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p, s, sec = await make.tree()
    a = await make.case(sec["id"], "A", automation_key="t.py::test_a")
    b = await make.case(sec["id"], "B")
    await client.post(f"/api/projects/{p['id']}/automation/jobs", json={"case_ids": [a["id"], b["id"]]})
    job = (await client.post(f"/api/projects/{p['id']}/automation/claim", json={"agent": "x"})).json()
    assert job["automation_keys"] == ["t.py::test_a"] and job["case_ids"] == [a["id"], b["id"]]
