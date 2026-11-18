"""Project role lists and bulk editing of cases."""

from httpx import AsyncClient


async def test_project_roles_list_rename_and_autocomplete(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p, _, sec = await make.tree()
    r = await client.patch(f"/api/projects/{p['id']}", json={"roles": [" Editor ", "Reviewer", "editor", ""]})
    assert r.status_code == 200 and r.json()["roles"] == ["Editor", "Reviewer"]

    # A role used on a case but missing from the list is added to it.
    c = await make.case(sec["id"], roles=["Reviewer", "Support Agent"])
    assert (await client.get(f"/api/projects/{p['id']}")).json()["roles"] == ["Editor", "Reviewer", "Support Agent"]
    await client.patch(f"/api/cases/{c['id']}", json={"roles": ["Customer"]})
    assert (await client.get(f"/api/projects/{p['id']}")).json()["roles"][-1] == "Customer"

    # Removing a role from the list keeps it on cases; pickers still offer it after the list.
    await client.patch(f"/api/projects/{p['id']}", json={"roles": ["Editor", "Reviewer"]})
    values = (await client.get(f"/api/projects/{p['id']}/case-values")).json()
    assert values["roles"] == ["Editor", "Reviewer", "Customer"]

    # Renaming updates the list and every case; renaming onto an existing role merges.
    other = await make.case(sec["id"], roles=["Editor", "Reviewer"])
    r = await client.post(f"/api/projects/{p['id']}/roles/rename", json={"old": "editor", "new": "Reviewer"})
    assert r.status_code == 200 and r.json()["roles"] == ["Reviewer"]
    assert (await client.get(f"/api/cases/{other['id']}")).json()["roles"] == ["Reviewer"]
    r = await client.post(f"/api/projects/{p['id']}/roles/rename", json={"old": "Reviewer", "new": "Approver"})
    assert r.json()["roles"] == ["Approver"]
    assert (await client.get(f"/api/cases/{other['id']}")).json()["roles"] == ["Approver"]
    r = await client.post(f"/api/projects/{p['id']}/roles/rename", json={"old": "Ghost", "new": "X"})
    assert r.status_code == 404


async def test_bulk_update(client: AsyncClient, make, tester: AsyncClient) -> None:  # type: ignore[no-untyped-def]
    p, _, sec = await make.tree()
    a = await make.case(sec["id"], "A", tags=["smoke", "old"], roles=["Editor"], owner="Jane")
    b = await make.case(sec["id"], "B", tags=["old"], sprint="Sprint 1")

    r = await tester.post("/api/cases/bulk-update", json={
        "case_ids": [a["id"], b["id"]],
        "set": {"state": "outdated", "priority": "high", "owner": None, "sprint": "Sprint 2"},
        "add_tags": ["Regression"], "remove_tags": ["old"],
        "add_roles": ["Reviewer", "editor"], "remove_roles": [],
    })
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 2}
    ca = (await client.get(f"/api/cases/{a['id']}")).json()
    cb = (await client.get(f"/api/cases/{b['id']}")).json()
    for c in (ca, cb):
        assert (c["state"], c["priority"], c["owner"], c["sprint"]) == ("outdated", "high", None, "Sprint 2")
        assert "old" not in c["tags"] and "regression" in c["tags"]
        assert c["updated_by"] == "Tom Tester"
    assert ca["tags"] == ["smoke", "regression"] and ca["roles"] == ["Editor", "Reviewer"]
    assert cb["roles"] == ["Reviewer", "editor"]
    assert ca["type"] == a["type"]  # untouched fields stay

    r = await client.post("/api/cases/bulk-update", json={"case_ids": [a["id"]], "remove_roles": ["EDITOR"]})
    assert (await client.get(f"/api/cases/{a['id']}")).json()["roles"] == ["Reviewer"]
    assert "Reviewer" in (await client.get(f"/api/projects/{p['id']}")).json()["roles"]

    assert (await client.post("/api/cases/bulk-update", json={"case_ids": [a["id"], 999999]})).status_code == 404
    p2, _, sec2 = await make.tree()
    elsewhere = await make.case(sec2["id"])
    r = await client.post("/api/cases/bulk-update", json={"case_ids": [a["id"], elsewhere["id"]]})
    assert r.status_code == 400
    r = await client.post("/api/cases/bulk-update", json={"case_ids": [a["id"]], "set": {"state": "bogus"}})
    assert r.status_code == 422
