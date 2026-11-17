"""Manual test runs: creation from selections, results/history, stats, closing."""

import pytest
from httpx import AsyncClient


@pytest.fixture
async def data(make):  # type: ignore[no-untyped-def]
    p = await make.project()
    web = await make.suite(p["id"], "Web")
    api = await make.suite(p["id"], "API")
    auth = await make.section(web["id"], "Auth")
    login = await make.section(web["id"], "Login", parent_id=auth["id"])
    cart = await make.section(web["id"], "Cart")
    orders = await make.section(api["id"], "Orders")
    c = {
        "auth": await make.case(auth["id"], "Auth overview"),
        "login": await make.case(login["id"], "Login", tags=["smoke"]),
        "cart": await make.case(cart["id"], "Cart", tags=["smoke"], priority="high"),
        "orders": await make.case(orders["id"], "Create order", priority="high"),
    }
    return {"p": p, "web": web, "api": api, "auth": auth, "login": login, "cart": cart, "c": c}


async def _run(client: AsyncClient, pid: int, **body):  # type: ignore[no-untyped-def]
    r = await client.post(f"/api/projects/{pid}/runs", json={"name": "Run", **body})
    assert r.status_code == 201, r.text
    return r.json()


async def _case_ids(client: AsyncClient, run_id: int) -> set[int]:
    return {x["case_id"] for x in (await client.get(f"/api/runs/{run_id}/cases")).json()}


async def test_create_run_from_selections(client: AsyncClient, data) -> None:  # type: ignore[no-untyped-def]
    pid, c = data["p"]["id"], data["c"]
    run = await _run(client, pid, suite_id=data["web"]["id"])
    assert run["source"] == "manual" and run["closed"] is False
    assert run["stats"] == {"total": 3, "untested": 3, "passed": 0, "failed": 0, "blocked": 0,
                            "skipped": 0, "retest": 0}

    run = await _run(client, pid, section_ids=[data["auth"]["id"]])  # includes subsections
    assert await _case_ids(client, run["id"]) == {c["auth"]["id"], c["login"]["id"]}

    run = await _run(client, pid, filter={"tags": ["smoke"]})
    assert await _case_ids(client, run["id"]) == {c["login"]["id"], c["cart"]["id"]}

    # Union of selectors, duplicates collapse.
    run = await _run(client, pid, case_ids=[c["orders"]["id"], c["cart"]["id"]],
                     filter={"priority": ["high"]})
    assert await _case_ids(client, run["id"]) == {c["orders"]["id"], c["cart"]["id"]}

    # Empty runs are allowed; cases can be added later.
    run = await _run(client, pid)
    assert run["stats"]["total"] == 0
    r = await client.post(f"/api/runs/{run['id']}/cases", json={"case_ids": [c["auth"]["id"]]})
    assert r.json()["stats"]["total"] == 1


async def test_create_run_rejects_foreign_cases(client: AsyncClient, data, make) -> None:  # type: ignore[no-untyped-def]
    _, _, other_sec = await make.tree()
    other = await make.case(other_sec["id"])
    r = await client.post(f"/api/projects/{data['p']['id']}/runs",
                          json={"name": "R", "case_ids": [other["id"]]})
    assert r.status_code == 400
    assert f"C{other['id']}" in r.json()["detail"]


async def test_results_history_and_current_status(client: AsyncClient, data) -> None:  # type: ignore[no-untyped-def]
    pid, c = data["p"]["id"], data["c"]
    run = await _run(client, pid, suite_id=data["web"]["id"])
    rid, login = run["id"], c["login"]["id"]

    r = await client.post(f"/api/runs/{rid}/results", json={"case_id": login, "status": "failed",
                                                            "comment": "Button missing"})
    assert r.status_code == 201
    await client.post(f"/api/runs/{rid}/results", json={"case_id": login, "status": "passed",
                                                       "comment": "Fixed"})
    cases = {x["case_id"]: x for x in (await client.get(f"/api/runs/{rid}/cases")).json()}
    assert cases[login]["status"] == "passed"
    assert cases[login]["result_count"] == 2
    assert cases[login]["last_result"]["comment"] == "Fixed"
    assert cases[c["auth"]["id"]]["status"] == "untested"
    assert cases[c["auth"]["id"]]["last_result"] is None
    assert cases[login]["section_path"] == "Auth > Login"

    hist = (await client.get(f"/api/runs/{rid}/cases/C{login}/results")).json()
    assert [h["status"] for h in hist] == ["passed", "failed"]

    stats = (await client.get(f"/api/runs/{rid}")).json()["stats"]
    assert (stats["passed"], stats["untested"], stats["total"]) == (1, 2, 3)

    # Filter run cases by status.
    r = await client.get(f"/api/runs/{rid}/cases", params={"status": "untested"})
    assert {x["case_id"] for x in r.json()} == {c["auth"]["id"], c["cart"]["id"]}


async def test_run_cases_in_tree_order(client: AsyncClient, data) -> None:  # type: ignore[no-untyped-def]
    run = await _run(client, data["p"]["id"], suite_id=data["web"]["id"])
    titles = [x["title"] for x in (await client.get(f"/api/runs/{run['id']}/cases")).json()]
    assert titles == ["Auth overview", "Login", "Cart"]


async def test_result_for_case_not_in_run(client: AsyncClient, data) -> None:  # type: ignore[no-untyped-def]
    run = await _run(client, data["p"]["id"], case_ids=[data["c"]["auth"]["id"]])
    r = await client.post(f"/api/runs/{run['id']}/results",
                          json={"case_id": data["c"]["orders"]["id"], "status": "passed"})
    assert r.status_code == 400


async def test_bulk_results(client: AsyncClient, data) -> None:  # type: ignore[no-untyped-def]
    c = data["c"]
    run = await _run(client, data["p"]["id"], suite_id=data["web"]["id"])
    r = await client.post(f"/api/runs/{run['id']}/results/bulk", json={"results": [
        {"case_id": c["auth"]["id"], "status": "blocked", "comment": "env down"},
        {"case_id": c["cart"]["id"], "status": "passed", "duration_ms": 1200},
    ]})
    assert r.status_code == 201 and len(r.json()) == 2
    stats = (await client.get(f"/api/runs/{run['id']}")).json()["stats"]
    assert (stats["blocked"], stats["passed"], stats["untested"]) == (1, 1, 1)


async def test_closed_run_is_read_only(client: AsyncClient, data) -> None:  # type: ignore[no-untyped-def]
    c = data["c"]
    run = await _run(client, data["p"]["id"], case_ids=[c["auth"]["id"]])
    r = await client.patch(f"/api/runs/{run['id']}", json={"closed": True})
    assert r.json()["closed"] is True and r.json()["closed_at"] is not None

    r = await client.post(f"/api/runs/{run['id']}/results", json={"case_id": c["auth"]["id"], "status": "passed"})
    assert r.status_code == 409
    r = await client.post(f"/api/runs/{run['id']}/cases", json={"case_ids": [c["cart"]["id"]]})
    assert r.status_code == 409

    r = await client.patch(f"/api/runs/{run['id']}", json={"closed": False})
    assert r.json()["closed_at"] is None
    r = await client.post(f"/api/runs/{run['id']}/results", json={"case_id": c["auth"]["id"], "status": "passed"})
    assert r.status_code == 201


async def test_remove_case_from_run(client: AsyncClient, data) -> None:  # type: ignore[no-untyped-def]
    c = data["c"]
    run = await _run(client, data["p"]["id"], case_ids=[c["auth"]["id"], c["cart"]["id"]])
    await client.post(f"/api/runs/{run['id']}/results", json={"case_id": c["auth"]["id"], "status": "failed"})
    assert (await client.delete(f"/api/runs/{run['id']}/cases/C{c['auth']['id']}")).status_code == 204
    assert await _case_ids(client, run["id"]) == {c["cart"]["id"]}
    assert (await client.get(f"/api/runs/{run['id']}/cases/{c['auth']['id']}/results")).json() == []
    assert (await client.delete(f"/api/runs/{run['id']}/cases/{c['auth']['id']}")).status_code == 404


async def test_list_runs_and_case_history(client: AsyncClient, data) -> None:  # type: ignore[no-untyped-def]
    pid, login = data["p"]["id"], data["c"]["login"]["id"]
    r1 = await _run(client, pid, name="First", case_ids=[login])
    r2 = await _run(client, pid, name="Second", case_ids=[login])
    await _run(client, pid, name="Other", case_ids=[data["c"]["cart"]["id"]])
    await client.post(f"/api/runs/{r1['id']}/results", json={"case_id": login, "status": "failed",
                                                            "error_message": "boom"})
    await client.patch(f"/api/runs/{r1['id']}", json={"closed": True})

    runs = (await client.get(f"/api/projects/{pid}/runs")).json()
    assert runs["total"] == 3
    assert [r["name"] for r in runs["items"]] == ["Other", "Second", "First"]
    assert runs["items"][2]["stats"]["failed"] == 1
    open_runs = (await client.get(f"/api/projects/{pid}/runs", params={"closed": False})).json()
    assert open_runs["total"] == 2

    hist = (await client.get(f"/api/cases/C{login}/history")).json()
    assert [(h["run_name"], h["status"]) for h in hist] == [("Second", "untested"), ("First", "failed")]
    assert hist[1]["last_result"]["error_message"] == "boom"
    assert hist[1]["run_closed"] is True and hist[0]["last_result"] is None
    assert r2["id"] == hist[0]["run_id"]


async def test_delete_run(client: AsyncClient, data) -> None:  # type: ignore[no-untyped-def]
    run = await _run(client, data["p"]["id"], suite_id=data["web"]["id"])
    assert (await client.delete(f"/api/runs/{run['id']}")).status_code == 204
    assert (await client.get(f"/api/runs/{run['id']}")).status_code == 404
    # Cases survive.
    assert (await client.get(f"/api/cases/{data['c']['auth']['id']}")).status_code == 200
