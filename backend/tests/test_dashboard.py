"""The project dashboard: coverage, review queue, results, failing and flaky cases."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import update

from app.db import SessionLocal
from app.models import TestResult


async def test_dashboard(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p, s, sec = await make.tree()
    sub = await make.section(s["id"], "Payments", parent_id=sec["id"])
    other = await make.section(s["id"], "Profile")
    a = await make.case(sub["id"], "Pay", automation_status="automated", priority="critical")
    b = await make.case(sec["id"], "Refund", automation_status="automated", state="pending_review")
    c = await make.case(sec["id"], "Cancel", automation_status="to_be_automated", priority="high")
    d = await make.case(other["id"], "Avatar", automation_progress="cannot_be_automated")
    await make.case(other["id"], "Old", automation_status="automated", state="outdated")  # not counted
    pid = p["id"]

    run = (await client.post(f"/api/projects/{pid}/runs", json={"name": "R", "suite_id": s["id"]})).json()
    for case, statuses in ((a, ["passed", "failed", "passed", "failed"]), (b, ["failed", "failed"]),
                           (c, ["passed"]), (d, ["skipped"])):
        for st in statuses:
            r = await client.post(f"/api/runs/{run['id']}/results", json={"case_id": case["id"], "status": st})
            assert r.status_code == 201
    # One result from the period before: it counts for the previous pass rate only.
    old = await client.post(f"/api/runs/{run['id']}/results", json={"case_id": c["id"], "status": "failed"})
    async with SessionLocal() as session:
        await session.execute(update(TestResult).where(TestResult.id == old.json()["id"])
                              .values(created_at=datetime.now(UTC) - timedelta(days=10)))
        await session.commit()

    r = await client.get(f"/api/projects/{pid}/dashboard", params={"days": 7})
    assert r.status_code == 200, r.text
    dash = r.json()
    assert dash["cases_total"] == 5 and dash["states"]["pending_review"] == 1 and dash["states"]["outdated"] == 1
    cov = dash["coverage"]
    assert (cov["live"], cov["automated"], cov["to_be_automated"], cov["manual"], cov["cannot_be_automated"]) == (4, 2, 1, 1, 1)
    assert cov["percent"] == 50.0 and cov["automatable_percent"] == 66.7
    assert {x["priority"]: (x["total"], x["automated"]) for x in dash["priorities"]} == {
        "critical": (1, 1), "high": (1, 0), "medium": (2, 1), "low": (0, 0)}
    assert dash["suites"] == [{"id": s["id"], "name": "S", "total": 4, "automated": 2, "to_be_automated": 1,
                               "pending_review": 1}]
    assert [(x["name"], x["total"], x["automated"]) for x in dash["areas"]] == [("Sec", 3, 2), ("Profile", 1, 0)]
    assert dash["review"]["count"] == 1 and dash["review"]["suite_id"] == s["id"]

    res = dash["results"]
    assert (res["recorded"], res["executed"], res["passed"], res["tested_cases"]) == (8, 7, 3, 4)
    assert res["pass_rate"] == 42.9 and res["previous_pass_rate"] == 0.0
    assert len(res["days"]) == 7 and res["days"][-1]["failed"] == 4 and res["days"][-1]["skipped"] == 1

    assert [(x["title"], x["count"], x["last_status"]) for x in dash["failing"]] == [("Refund", 2, "failed"),  # latest
                                                                                    ("Pay", 2, "failed")]
    assert [(x["title"], x["count"]) for x in dash["flaky"]] == [("Pay", 3)]
    assert [x["id"] for x in dash["runs"]] == [run["id"]] and dash["runs_in_period"] == 1
    assert dash["automation"]["agents"] == 0

    assert (await client.get("/api/projects/999999/dashboard")).status_code == 404
    assert (await client.get(f"/api/projects/{pid}/dashboard", params={"days": 0})).status_code == 422


async def test_dashboard_empty_project(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p = await make.project()
    dash = (await client.get(f"/api/projects/{p['id']}/dashboard")).json()
    assert dash["coverage"]["percent"] is None and dash["results"]["pass_rate"] is None
    assert len(dash["results"]["days"]) == 30 and dash["failing"] == [] and dash["review"]["suite_id"] is None
