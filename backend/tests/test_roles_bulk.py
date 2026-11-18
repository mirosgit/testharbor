"""Project role lists and bulk editing of cases."""

from httpx import AsyncClient


async def test_project_roles_list_rename_and_autocomplete(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p, _, sec = await make.tree()
    r = await client.patch(f"/api/projects/{p['id']}", json={"roles": [" Nurse ", "Doctor", "nurse", ""]})
    assert r.status_code == 200 and r.json()["roles"] == ["Nurse", "Doctor"]

    # A role used on a case but missing from the list is added to it.
    c = await make.case(sec["id"], roles=["Doctor", "Care Coach"])
    assert (await client.get(f"/api/projects/{p['id']}")).json()["roles"] == ["Nurse", "Doctor", "Care Coach"]
    await client.patch(f"/api/cases/{c['id']}", json={"roles": ["Patient"]})
    assert (await client.get(f"/api/projects/{p['id']}")).json()["roles"][-1] == "Patient"

    # Removing a role from the list keeps it on cases; pickers still offer it after the list.
    await client.patch(f"/api/projects/{p['id']}", json={"roles": ["Nurse", "Doctor"]})
    values = (await client.get(f"/api/projects/{p['id']}/case-values")).json()
    assert values["roles"] == ["Nurse", "Doctor", "Patient"]

    # Renaming updates the list and every case; renaming onto an existing role merges.
    other = await make.case(sec["id"], roles=["Nurse", "Doctor"])
    r = await client.post(f"/api/projects/{p['id']}/roles/rename", json={"old": "nurse", "new": "Doctor"})
    assert r.status_code == 200 and r.json()["roles"] == ["Doctor"]
    assert (await client.get(f"/api/cases/{other['id']}")).json()["roles"] == ["Doctor"]
    r = await client.post(f"/api/projects/{p['id']}/roles/rename", json={"old": "Doctor", "new": "Physician"})
    assert r.json()["roles"] == ["Physician"]
    assert (await client.get(f"/api/cases/{other['id']}")).json()["roles"] == ["Physician"]
    r = await client.post(f"/api/projects/{p['id']}/roles/rename", json={"old": "Ghost", "new": "X"})
    assert r.status_code == 404


async def test_bulk_update(client: AsyncClient, make, tester: AsyncClient) -> None:  # type: ignore[no-untyped-def]
    p, _, sec = await make.tree()
    a = await make.case(sec["id"], "A", tags=["smoke", "old"], roles=["Nurse"], owner="Jane")
    b = await make.case(sec["id"], "B", tags=["old"], sprint="Sprint 1")

    r = await tester.post("/api/cases/bulk-update", json={
        "case_ids": [a["id"], b["id"]],
        "set": {"state": "outdated", "priority": "high", "owner": None, "sprint": "Sprint 2"},
        "add_tags": ["Regression"], "remove_tags": ["old"],
        "add_roles": ["Doctor", "nurse"], "remove_roles": [],
    })
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 2}
    ca = (await client.get(f"/api/cases/{a['id']}")).json()
    cb = (await client.get(f"/api/cases/{b['id']}")).json()
    for c in (ca, cb):
        assert (c["state"], c["priority"], c["owner"], c["sprint"]) == ("outdated", "high", None, "Sprint 2")
        assert "old" not in c["tags"] and "regression" in c["tags"]
        assert c["updated_by"] == "Tom Tester"
    assert ca["tags"] == ["smoke", "regression"] and ca["roles"] == ["Nurse", "Doctor"]
    assert cb["roles"] == ["Doctor", "nurse"]
    assert ca["type"] == a["type"]  # untouched fields stay

    r = await client.post("/api/cases/bulk-update", json={"case_ids": [a["id"]], "remove_roles": ["NURSE"]})
    assert (await client.get(f"/api/cases/{a['id']}")).json()["roles"] == ["Doctor"]
    assert "Doctor" in (await client.get(f"/api/projects/{p['id']}")).json()["roles"]

    assert (await client.post("/api/cases/bulk-update", json={"case_ids": [a["id"], 999999]})).status_code == 404
    p2, _, sec2 = await make.tree()
    elsewhere = await make.case(sec2["id"])
    r = await client.post("/api/cases/bulk-update", json={"case_ids": [a["id"], elsewhere["id"]]})
    assert r.status_code == 400
    r = await client.post("/api/cases/bulk-update", json={"case_ids": [a["id"]], "set": {"state": "bogus"}})
    assert r.status_code == 422


async def test_import_creates_applicable_roles(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p = await make.project()
    s = await make.suite(p["id"])
    await client.patch(f"/api/projects/{p['id']}", json={"roles": ["ADMIN"]})
    csv_text = (
        "Test Case ID,Title,Folder Path,Applicable Roles\n"
        'TC-1,One,Area,"admin, Care Coach"\n'
        "TC-2,Two,Area,Care coach | Patient\n"
        "TC-3,Three,Area,\n"
    )

    async def imp(**params):  # type: ignore[no-untyped-def]
        r = await client.post(f"/api/suites/{s['id']}/import", params=params,
                              files={"file": ("export.csv", csv_text.encode(), "text/csv")})
        assert r.status_code == 200, r.text
        return r.json()

    # A preview changes nothing, including the project's role list.
    await imp(dry_run="true")
    assert (await client.get(f"/api/projects/{p['id']}")).json()["roles"] == ["ADMIN"]

    await imp()
    # New roles join the list once, in file order; existing ones keep the project's spelling.
    assert (await client.get(f"/api/projects/{p['id']}")).json()["roles"] == ["ADMIN", "Care Coach", "Patient"]
    cases = {c["external_id"]: c["roles"] for c in
             (await client.get(f"/api/projects/{p['id']}/cases")).json()["items"]}
    assert cases == {"TC-1": ["ADMIN", "Care Coach"], "TC-2": ["Care Coach", "Patient"], "TC-3": []}
