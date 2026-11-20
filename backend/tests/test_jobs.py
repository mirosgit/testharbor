"""Running automated tests from TestHarbor through an agent."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import update

from app.db import SessionLocal
from app.models import AutomationJob


async def test_job_lifecycle_all_tests(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p, s, sec = await make.tree()
    await make.case(sec["id"], "Login")

    # No agent has polled yet.
    assert (await client.get(f"/api/projects/{p['id']}/automation/agents")).json() == []
    r = await client.post(f"/api/projects/{p['id']}/automation/jobs", json={"name": "Nightly"})
    assert r.status_code == 201, r.text
    job = r.json()
    assert (job["status"], job["case_ids"], job["requested_by_name"]) == ("queued", [], "Ada Admin")
    run = (await client.get(f"/api/runs/{job['run_id']}")).json()
    assert (run["name"], run["source"]) == ("Nightly", "ci")

    # The agent claims it (and shows up as online); a second poll gets nothing.
    claim = await client.post(f"/api/projects/{p['id']}/automation/claim", json={"agent": "laptop"})
    assert claim.status_code == 200 and claim.json()["id"] == job["id"]
    assert claim.json()["status"] == "running" and claim.json()["agent"] == "laptop"
    assert (await client.post(f"/api/projects/{p['id']}/automation/claim", json={"agent": "laptop"})).status_code == 204
    agents = (await client.get(f"/api/projects/{p['id']}/automation/agents")).json()
    assert [(a["name"], a["online"]) for a in agents] == [("laptop", True)]

    # Output streams in; finishing records the exit code.
    ctl = await client.post(f"/api/automation/jobs/{job['id']}/progress", json={"log": "Running 1 test\n"})
    assert ctl.json() == {"cancelled": False}
    done = await client.post(f"/api/automation/jobs/{job['id']}/finish",
                             json={"status": "finished", "exit_code": 1, "log": "1 failed\n"})
    assert (done.json()["status"], done.json()["exit_code"]) == ("finished", 1)
    detail = (await client.get(f"/api/automation/jobs/{job['id']}")).json()
    assert detail["log"] == "Running 1 test\n1 failed\n" and detail["finished_at"]
    # A finished job tells a late agent to stop, and can't be finished twice.
    assert (await client.post(f"/api/automation/jobs/{job['id']}/progress", json={})).json() == {"cancelled": True}
    again = await client.post(f"/api/automation/jobs/{job['id']}/finish", json={"status": "error"})
    assert again.json()["status"] == "finished"
    listed = (await client.get(f"/api/projects/{p['id']}/automation/jobs", params={"run_id": job["run_id"]})).json()
    assert [j["id"] for j in listed] == [job["id"]]


async def test_selected_and_failed_cases(client: AsyncClient, make, tester: AsyncClient) -> None:  # type: ignore[no-untyped-def]
    p, s, sec = await make.tree()
    a = await make.case(sec["id"], "A")
    b = await make.case(sec["id"], "B")

    # A tester can start a job for chosen cases; they are added to the new run.
    r = await tester.post(f"/api/projects/{p['id']}/automation/jobs", json={"case_ids": [b["id"], a["id"]]})
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["case_ids"] == [b["id"], a["id"]]
    keys = {c["key"] for c in (await client.get(f"/api/runs/{job['run_id']}/cases")).json()}
    assert keys == {a["key"], b["key"]}
    # One active job per run.
    dup = await client.post(f"/api/projects/{p['id']}/automation/jobs", json={"run_id": job["run_id"]})
    assert dup.status_code == 409

    await client.post(f"/api/projects/{p['id']}/automation/claim", json={"agent": "ci-box"})
    await client.post(f"/api/runs/{job['run_id']}/results", json={"case_id": a["id"], "status": "failed"})
    await client.post(f"/api/runs/{job['run_id']}/results", json={"case_id": b["id"], "status": "passed"})
    await client.post(f"/api/automation/jobs/{job['id']}/finish", json={"status": "finished", "exit_code": 1})

    # Re-run only what failed, into the same run.
    rerun = await client.post(f"/api/projects/{p['id']}/automation/jobs",
                              json={"run_id": job["run_id"], "only_failed": True})
    assert rerun.status_code == 201 and rerun.json()["case_ids"] == [a["id"]]
    assert rerun.json()["run_id"] == job["run_id"]

    bad = await client.post(f"/api/projects/{p['id']}/automation/jobs", json={"case_ids": [999999]})
    assert bad.status_code == 400


async def test_cancel_and_stale_agent(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p, _, _ = await make.tree()
    queued = (await client.post(f"/api/projects/{p['id']}/automation/jobs", json={})).json()
    assert (await client.post(f"/api/automation/jobs/{queued['id']}/cancel")).json()["status"] == "cancelled"
    assert (await client.post(f"/api/projects/{p['id']}/automation/claim", json={"agent": "a"})).status_code == 204

    running = (await client.post(f"/api/projects/{p['id']}/automation/jobs", json={})).json()
    await client.post(f"/api/projects/{p['id']}/automation/claim", json={"agent": "a"})
    # Cancelling a running job tells the agent to stop on its next progress call.
    await client.post(f"/api/automation/jobs/{running['id']}/cancel")
    assert (await client.post(f"/api/automation/jobs/{running['id']}/progress", json={})).json() == {"cancelled": True}
    finished = await client.post(f"/api/automation/jobs/{running['id']}/finish", json={"status": "finished"})
    assert finished.json()["status"] == "cancelled"

    # An agent that goes silent: its job becomes an error.
    silent = (await client.post(f"/api/projects/{p['id']}/automation/jobs", json={})).json()
    await client.post(f"/api/projects/{p['id']}/automation/claim", json={"agent": "a"})
    async with SessionLocal() as s:
        await s.execute(update(AutomationJob).where(AutomationJob.id == silent["id"])
                        .values(heartbeat_at=datetime.now(UTC) - timedelta(minutes=5)))
        await s.commit()
    detail = (await client.get(f"/api/automation/jobs/{silent['id']}")).json()
    assert (detail["status"], detail["message"]) == ("error", "The agent stopped responding")


async def test_append_upload_fills_run_details(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p, _, sec = await make.tree()
    c = await make.case(sec["id"], "Login")
    job = (await client.post(f"/api/projects/{p['id']}/automation/jobs", json={})).json()
    xml = f'<testsuite><testcase name="{c["key"]} login" classname="t"/></testsuite>'.encode()
    r = await client.post(f"/api/projects/{p['id']}/runs/import-junit",
                          params={"run_id": job["run_id"], "branch": "main", "commit": "abc"},
                          files=[("file", ("j.xml", xml, "application/xml"))])
    assert r.status_code == 200, r.text
    run = (await client.get(f"/api/runs/{job['run_id']}")).json()
    assert (run["branch"], run["commit"], run["stats"]["passed"]) == ("main", "abc", 1)


async def test_agent_options_and_job_params(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p, s, sec = await make.tree()
    options = [
        {"name": "ENV", "label": "Environment", "type": "choice", "default": "dev",
         "choices": [{"value": "dev", "label": "dev"}, {"value": "qa", "label": "qa"}]},
        {"name": "ROLES", "label": "Roles", "type": "multi", "default": [], "hint": "None = every role",
         "choices": [{"value": "admin", "label": "Admin"}]},
        {"name": "HEADED", "type": "bool", "default": False},
    ]
    claim = await client.post(f"/api/projects/{p['id']}/automation/claim", json={"agent": "box", "options": options})
    assert claim.status_code == 204, claim.text
    (agent,) = (await client.get(f"/api/projects/{p['id']}/automation/agents")).json()
    assert agent["options"][0]["choices"][1] == {"value": "qa", "label": "qa"}
    assert agent["options"][2] == {"name": "HEADED", "label": "", "type": "bool", "choices": [], "default": False,
                                   "hint": None}

    params = {"ENV": "qa", "ROLES": ["admin"], "HEADED": True}
    job = (await client.post(f"/api/projects/{p['id']}/automation/jobs", json={"params": params})).json()
    assert job["params"] == params
    claimed = await client.post(f"/api/projects/{p['id']}/automation/claim", json={"agent": "box"})
    assert claimed.json()["params"] == params
    # An agent restarted without options offers none.
    (agent,) = (await client.get(f"/api/projects/{p['id']}/automation/agents")).json()
    assert agent["options"] == []

    for bad in ({"env": "qa"}, {"ENV": {"x": 1}}, {"ENV": "x" * 201}, {"PATH; rm": "1"}):
        r = await client.post(f"/api/projects/{p['id']}/automation/jobs", json={"params": bad})
        assert r.status_code == 422, bad
    bad_option = await client.post(f"/api/projects/{p['id']}/automation/claim",
                                   json={"agent": "box", "options": [{"name": "env", "type": "choice"}]})
    assert bad_option.status_code == 422
