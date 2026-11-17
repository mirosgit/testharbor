"""CSV / JSON import and export."""

import csv
import io
import json

from httpx import AsyncClient

from app.routers.io import steps_to_text, text_to_steps


def test_steps_text_roundtrip() -> None:
    steps = [
        {"action": "Open /login", "expected": "Form shown"},
        {"action": "Type\nmultiline", "expected": ""},
        {"action": "Submit", "expected": "Dashboard\n- avatar visible"},
    ]
    assert text_to_steps(steps_to_text(steps)) == steps


def test_unnumbered_steps_are_one_per_line() -> None:
    assert text_to_steps("Open app => It opens\n\nClick login") == [
        {"action": "Open app", "expected": "It opens"},
        {"action": "Click login", "expected": ""},
    ]


async def _seed(make):  # type: ignore[no-untyped-def]
    p = await make.project()
    s = await make.suite(p["id"], "Web App")
    auth = await make.section(s["id"], "Auth")
    login = await make.section(s["id"], "Login", parent_id=auth["id"])
    c = await make.case(login["id"], "Login works", priority="high", tags=["auth", "smoke"],
                        steps=[{"action": "Open", "expected": "Shown"}], automation_key="t::login")
    return p, s, login, c


async def test_csv_export(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    _, s, _, c = await _seed(make)
    r = await client.get(f"/api/suites/{s['id']}/export", params={"format": "csv"})
    assert r.status_code == 200
    assert 'filename="web-app-cases.csv"' in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert rows == [{
        "id": c["key"], "section_path": "Auth > Login", "title": "Login works", "preconditions": "",
        "steps": "1. Open => Shown", "expected_result": "", "priority": "high", "type": "functional",
        "tags": "auth, smoke", "automation_status": "manual", "automation_key": "t::login",
    }]


async def test_json_roundtrip_into_new_suite(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p, s, _, _ = await _seed(make)
    exported = (await client.get(f"/api/suites/{s['id']}/export", params={"format": "json"})).json()
    assert exported["format"] == "testharbor" and len(exported["cases"]) == 1

    # Importing into another suite: ids don't exist there -> new cases. Drop the
    # automation_key since keys are unique per project.
    for c in exported["cases"]:
        c["automation_key"] = None
    target = await make.suite(p["id"], "Copy")
    r = await client.post(
        f"/api/suites/{target['id']}/import",
        files={"file": ("cases.json", json.dumps(exported), "application/json")},
    )
    assert r.json() == {"created": 1, "updated": 0, "sections_created": 2, "errors": []}
    sections = (await client.get(f"/api/suites/{target['id']}/sections")).json()
    assert sorted(x["name"] for x in sections) == ["Auth", "Login"]
    copied = (await client.get(f"/api/projects/{p['id']}/cases", params={"suite_id": target["id"]})).json()
    item = copied["items"][0]
    assert (item["title"], item["priority"], item["tags"]) == ("Login works", "high", ["auth", "smoke"])
    assert item["steps"] == [{"action": "Open", "expected": "Shown"}]


async def test_csv_import_creates_updates_and_reports_errors(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p, s, login, c = await _seed(make)
    content = (
        "id,section_path,title,steps,priority,tags,automation_key\n"
        f'{c["key"]},,Login works (edited),"1. Open\n2. Submit => Ok",,auth,t::login\n'
        ',New > Deep,Brand new,Just one step,critical,"a, b",\n'
        ',,,,,,\n'
        ',Auth,Bad priority,,urgent,,\n'
        ',Auth,Dup key,,,,t::login\n'
    )
    r = await client.post(
        f"/api/suites/{s['id']}/import", files={"file": ("cases.csv", content, "text/csv")}
    )
    body = r.json()
    assert (body["created"], body["updated"], body["sections_created"]) == (1, 1, 2)
    assert len(body["errors"]) == 3
    assert body["errors"][0].startswith("row 4: title")
    assert "row 5: priority" in body["errors"][1]
    assert "already used by" in body["errors"][2]

    updated = (await client.get(f"/api/cases/{c['id']}")).json()
    assert updated["title"] == "Login works (edited)"
    assert updated["priority"] == "high"  # blank cell keeps the current value
    assert updated["section_id"] == login["id"]  # blank path keeps the section
    assert updated["steps"] == [{"action": "Open", "expected": ""}, {"action": "Submit", "expected": "Ok"}]
    assert updated["tags"] == ["auth"]

    new = (await client.get(f"/api/projects/{p['id']}/cases", params={"q": "Brand new"})).json()["items"][0]
    assert (new["priority"], new["tags"], new["steps"]) == (
        "critical", ["a", "b"], [{"action": "Just one step", "expected": ""}]
    )


async def test_csv_without_title_column_is_400(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    _, s, _, _ = await _seed(make)
    r = await client.post(f"/api/suites/{s['id']}/import", files={"file": ("x.csv", "a,b\n1,2\n", "text/csv")})
    assert r.status_code == 400


async def test_invalid_json_is_400(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    _, s, _, _ = await _seed(make)
    r = await client.post(f"/api/suites/{s['id']}/import", files={"file": ("x.json", "{oops", "application/json")})
    assert r.status_code == 400
