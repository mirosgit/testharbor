"""CSV / JSON import and export."""

import csv
import io
import json
from pathlib import Path

import pytest
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
        "id": c["key"], "external_id": "", "section_path": "Auth > Login", "title": "Login works", "preconditions": "",
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
    assert r.json() == {"created": 1, "updated": 0, "sections_created": 2, "errors": [],
                        "warnings": [], "ignored_columns": [], "extra_columns": [],
                        "section_id": None, "dry_run": False}
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
        ',Auth,Bad priority,,sometimes,,\n'
        ',Auth,Dup key,,,,t::login\n'
    )
    r = await client.post(
        f"/api/suites/{s['id']}/import", files={"file": ("cases.csv", content, "text/csv")}
    )
    body = r.json()
    # Blank rows are skipped; an unknown priority is imported as medium with a warning.
    assert (body["created"], body["updated"], body["sections_created"]) == (2, 1, 2)
    assert body["warnings"] == ["row 5: priority 'sometimes' not recognized, used medium"]
    assert len(body["errors"]) == 1 and body["errors"][0].startswith("row 6: automation_key")
    assert "already used by" in body["errors"][0]

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


# --- Other tools' exports ----------------------------------------------------------------

from app.case_import import map_automation, map_priority, map_type, parse_csv, unwrap  # noqa: E402

BROWSERSTACK = (Path(__file__).parent / "fixtures" / "csv" / "browserstack-export.csv").read_text()


def test_unwrap_hard_wrapped_lists() -> None:
    text = "1.  Order has status, with\n    filled in details\n2.  Done\n   - nested item stays\n"
    assert unwrap(text) == "1. Order has status, with filled in details\n2. Done\n   - nested item stays"


@pytest.mark.parametrize(("value", "expected"), [
    ("High", "high"), ("Highest", "critical"), ("1 - Critical", "critical"), ("Normal", "medium"),
    ("trivial", "low"), ("", None), ("Undefined", None),
])
def test_map_priority(value: str, expected: str | None) -> None:
    p, warning = map_priority(value)
    assert (p.value if p else None) == expected and warning is None


@pytest.mark.parametrize(("value", "expected"), [
    ("Automated", "automated"), ("Not Automated", "manual"), ("Cannot Be Automated", "manual"),
    ("Can Not Be Automated", "manual"), ("In Progress", "to_be_automated"),
    ("To Be Automated", "to_be_automated"), ("Manual", "manual"), ("", None),
])
def test_map_automation(value: str, expected: str | None) -> None:
    a, warning = map_automation(value)
    assert (a.value if a else None) == expected and warning is None


def test_unknown_values_warn() -> None:
    assert map_priority("Whatever") == (None, "priority 'Whatever' not recognized, used medium")
    assert map_type("Undefined") == (None, None)
    assert map_type("Usability")[0].value == "other"
    assert map_automation("Someday")[1] is not None


def test_parse_browserstack_export() -> None:
    parsed = parse_csv(BROWSERSTACK)
    assert not parsed.own_format and len(parsed.rows) == 4
    first, second = parsed.rows[0], parsed.rows[1]
    assert first["external_id"] == "TC-101" and first["section_path"] == "Orders>Active>Cancellation"
    assert (first["priority"], first["type"], first["automation_status"]) == ("high", "regression", "manual")
    assert first["preconditions"] == (
        "1. User signed in as admin\n2. At least one active order exists\n"
        "3. Order has at least 1 item linked to a warehouse shipment"
    )
    assert first["steps"][4] == {"action": "Enter details in the text field and submit the form", "expected": ""}
    assert len(first["steps"]) == 5
    assert first["expected_result"] == (
        "1. Order has Cancelled status and reason: Other, with filled in details\n"
        "2. Warehouse received a note with correct reason"
    )
    assert first["tags"] == ["order_cancellation", "warehouse", "regression"]
    # Description goes on top of the preconditions; "Undefined" type falls back to the default.
    assert second["preconditions"].startswith("Coupons must not survive a restore.\n\n1. User")
    assert (second["type"], second["automation_status"]) == (None, "manual")
    assert parsed.rows[2]["priority"] == "critical"
    assert parsed.rows[3]["steps"] == [{"action": "Just one unnumbered step", "expected": ""}]
    # Extra columns become custom fields, except tool-internal ones; empty columns are not offered.
    assert parsed.ignored_columns == ["Folder ID", "Template Type", "Template Name", "Project Name", "Test Case URL"]
    assert dict(parsed.extra_columns)["Owner"] is True and "Issues" not in dict(parsed.extra_columns)
    assert first["custom_fields"] == [
        {"name": "State", "value": "Active"}, {"name": "Owner", "value": "Jane Doe"},
        {"name": "Automation Complexity", "value": "Not Applicable"},
        {"name": "Automation Status (custom)", "value": "Can Not Be Automated"},
        {"name": "Sprint No.", "value": "Sprint 12"}, {"name": "Created At", "value": "06/22/2026 09:26:20"},
        {"name": "Last Updated At", "value": "06/22/2026 11:27:39"}, {"name": "Last Updated By", "value": "jdoe"},
    ]
    # Pick columns explicitly (case-insensitive); everything else is ignored.
    picked = parse_csv(BROWSERSTACK, {"owner", "SPRINT NO."})
    assert picked.rows[0]["custom_fields"] == [{"name": "Owner", "value": "Jane Doe"},
                                               {"name": "Sprint No.", "value": "Sprint 12"}]
    assert "State" in picked.ignored_columns
    # Records are numbered like spreadsheet rows (header = 1), even with multi-line cells.
    assert parsed.warnings == [
        "row 5: priority 'Whatever' not recognized, used medium",
        "row 5: automation status 'Someday' not recognized, used manual",
    ]
    assert parsed.rows[3]["type"] == "other"  # "Usability" is a known synonym


async def _import_csv(client: AsyncClient, suite_id: int, content: str, **params):  # type: ignore[no-untyped-def]
    r = await client.post(f"/api/suites/{suite_id}/import", params=params,
                          files={"file": ("export.csv", content.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


async def test_import_browserstack_into_new_section_and_reimport(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p = await make.project()
    s = await make.suite(p["id"])
    body = await _import_csv(client, s["id"], BROWSERSTACK, new_section="Shop [web]")
    assert (body["created"], body["updated"], body["errors"]) == (4, 0, [])
    assert body["sections_created"] == 5  # Shop [web], Orders, Active, Cancellation, Bulk
    assert len(body["warnings"]) == 2 and "Test Case URL" in body["ignored_columns"]

    sections = {x["id"]: x for x in (await client.get(f"/api/suites/{s['id']}/sections")).json()}
    assert sections[body["section_id"]]["name"] == "Shop [web]"
    cases = (await client.get(f"/api/projects/{p['id']}/cases",
                              params={"section_id": body["section_id"]})).json()["items"]
    by_ext = {c["external_id"]: c for c in cases}
    assert set(by_ext) == {"TC-101", "TC-102", "TC-103", "TC-104"}
    leaf = sections[by_ext["TC-101"]["section_id"]]
    assert leaf["name"] == "Cancellation"

    # Search finds cases by their external id.
    found = (await client.get(f"/api/projects/{p['id']}/cases", params={"q": "tc-102"})).json()["items"]
    assert [c["external_id"] for c in found] == ["TC-102"]

    # Re-importing the same file updates instead of duplicating.
    again = await _import_csv(client, s["id"], BROWSERSTACK, new_section="Shop [web]")
    assert (again["created"], again["updated"], again["sections_created"]) == (0, 4, 0)


async def test_import_into_existing_section_flat(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p = await make.project()
    s = await make.suite(p["id"])
    target = await make.section(s["id"], "Regression pack")
    body = await _import_csv(client, s["id"], BROWSERSTACK, section_id=target["id"], keep_paths="false")
    assert (body["created"], body["sections_created"], body["section_id"]) == (4, 0, target["id"])
    cases = (await client.get(f"/api/projects/{p['id']}/cases", params={"suite_id": s["id"]})).json()["items"]
    assert {c["section_id"] for c in cases} == {target["id"]}
    r = await client.post(f"/api/suites/{s['id']}/import", params={"section_id": 999},
                          files={"file": ("x.csv", BROWSERSTACK.encode(), "text/csv")})
    assert r.status_code == 400


async def test_import_without_target_keeps_old_behaviour(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p = await make.project()
    s = await make.suite(p["id"])
    await _import_csv(client, s["id"], "title\nNo folder\n")
    await _import_csv(client, s["id"], BROWSERSTACK)
    names = sorted(x["name"] for x in (await client.get(f"/api/suites/{s['id']}/sections")).json()
                   if x["parent_id"] is None)
    assert names == ["Imported", "Orders"]


async def test_semicolon_csv_and_testrail_ids(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p = await make.project()
    s = await make.suite(p["id"])
    sec = await make.section(s["id"])
    mine = await make.case(sec["id"], "Unrelated existing case")  # C1 in this suite
    content = 'ID;Title;Section Hierarchy;Priority;Type\nC1;Login;Auth > Login;1 - Critical;Functional\n'
    body = await _import_csv(client, s["id"], content)
    # A foreign "C1" is an external id, never our C1.
    assert (body["created"], body["updated"]) == (1, 0)
    assert (await client.get(f"/api/cases/{mine['id']}")).json()["title"] == "Unrelated existing case"
    new = (await client.get(f"/api/projects/{p['id']}/cases", params={"q": "Login"})).json()["items"][0]
    assert (new["external_id"], new["priority"]) == ("C1", "critical")


# --- Custom fields ---------------------------------------------------------------------


async def test_custom_fields_import_preview_merge_filter_export(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    p = await make.project()
    s = await make.suite(p["id"])

    # Dry run: report only, nothing saved.
    preview = await _import_csv(client, s["id"], BROWSERSTACK, new_section="Shop", dry_run="true")
    assert preview["dry_run"] is True and preview["created"] == 4
    assert {c["name"]: c["selected"] for c in preview["extra_columns"]}["Folder ID"] is False
    assert (await client.get(f"/api/suites/{s['id']}/sections")).json() == []

    body = await _import_csv(client, s["id"], BROWSERSTACK, new_section="Shop",
                             columns=["Owner", "State", "Sprint No."])
    assert body["created"] == 4 and "Created At" in body["ignored_columns"]
    case = (await client.get(f"/api/projects/{p['id']}/cases", params={"q": "TC-101"})).json()["items"][0]
    assert case["custom_fields"] == [{"name": "State", "value": "Active"}, {"name": "Owner", "value": "Jane Doe"},
                                     {"name": "Sprint No.", "value": "Sprint 12"}]

    # A field added by hand survives a re-import; imported ones are refreshed.
    fields = case["custom_fields"] + [{"name": "Reviewer", "value": "Ann"}]
    fields[0] = {"name": "State", "value": "Draft"}
    await client.patch(f"/api/cases/{case['id']}", json={"custom_fields": fields})
    await _import_csv(client, s["id"], BROWSERSTACK, new_section="Shop", columns=["Owner", "State", "Sprint No."])
    after = (await client.get(f"/api/cases/{case['id']}")).json()["custom_fields"]
    assert after == [{"name": "State", "value": "Active"}, {"name": "Owner", "value": "Jane Doe"},
                     {"name": "Sprint No.", "value": "Sprint 12"}, {"name": "Reviewer", "value": "Ann"}]

    # Field values for filters, and filtering (same name: any value; different names: all).
    listing = {f["name"]: f["values"] for f in (await client.get(f"/api/projects/{p['id']}/custom-fields")).json()}
    assert listing["Owner"] == ["Jane Doe", "John Roe"] and listing["Sprint No."] == ["Sprint 12", "Sprint 13"]

    async def ext(**params):  # type: ignore[no-untyped-def]
        r = await client.get(f"/api/projects/{p['id']}/cases", params=params)
        assert r.status_code == 200, r.text
        return sorted(c["external_id"] for c in r.json()["items"])

    assert await ext(field="Owner=Jane Doe") == ["TC-101", "TC-103", "TC-104"]
    assert await ext(field=["Owner=Jane Doe", "Sprint No.=Sprint 12"]) == ["TC-101", "TC-103"]
    assert await ext(field=["Sprint No.=Sprint 12", "Sprint No.=Sprint 13"]) == ["TC-101", "TC-102", "TC-103"]
    assert (await client.get(f"/api/projects/{p['id']}/cases", params={"field": "nope"})).status_code == 422

    # Export has a column per field; importing that export into another suite keeps them.
    exported = (await client.get(f"/api/suites/{s['id']}/export", params={"format": "csv"})).text
    header = next(csv.reader(io.StringIO(exported)))
    assert header[-4:] == ["State", "Owner", "Sprint No.", "Reviewer"]
    other = await make.suite(p["id"], "Copy")
    copied = await _import_csv(client, other["id"], exported.replace("TC-", "XC-"))
    assert copied["created"] == 4 and copied["ignored_columns"] == []
    c2 = (await client.get(f"/api/projects/{p['id']}/cases", params={"q": "XC-101"})).json()["items"][0]
    assert {f["name"] for f in c2["custom_fields"]} == {"State", "Owner", "Sprint No.", "Reviewer"}


async def test_custom_fields_validation(client: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    _, _, sec = await make.tree()
    c = await make.case(sec["id"], custom_fields=[{"name": "  Sprint  No. ", "value": " 12 "},
                                                 {"name": "Empty", "value": "  "}])
    assert c["custom_fields"] == [{"name": "Sprint No.", "value": "12"}]
    r = await client.patch(f"/api/cases/{c['id']}", json={"custom_fields": [
        {"name": "Owner", "value": "a"}, {"name": "owner", "value": "b"}]})
    assert r.status_code == 422
    # Omitting custom_fields in a PATCH leaves them alone.
    r = await client.patch(f"/api/cases/{c['id']}", json={"title": "Renamed"})
    assert r.json()["custom_fields"] == [{"name": "Sprint No.", "value": "12"}]
