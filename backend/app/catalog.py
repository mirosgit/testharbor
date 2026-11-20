"""Sync the automated tests' catalog into test cases.

An agent reports the tests it can run (`testcli agent --catalog FILE`): a stable key per test
(e.g. a pytest-bdd scenario's node id), a title, a section path, a description, preconditions,
steps, roles, tags and the case ids it is tagged with. A person reviews a preview and applies it:

* A test tagged with a case id, or whose key is a case's automation key, belongs to that case.
  - A case created from the catalog (`catalog_managed`) follows the test: title, description,
    preconditions, steps, roles and tags are rewritten when they change.
  - Any other case is a person's case: only its automation key and status are set (link).
* A new test becomes a case in the "Autotests" suite, in sections built from its path, unless the
  person links it to an existing case (similar titles are suggested, so manual cases are not
  duplicated).
* A catalog case whose test is gone becomes Outdated; it is never deleted.

Matching results to cases needs nothing new: reports carry the same keys as `automation_key`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AutomationStatus,
    CaseState,
    CaseType,
    Project,
    Section,
    Suite,
    TestCase,
)
from app.schemas import CatalogTest, role_key
from app.services import next_case_position, remember_roles, section_paths

AUTOTESTS_SUITE = "Autotests"
NO_PATH_SECTION = "Other"
SUGGESTION_MIN_SCORE = 0.45
MAX_SUGGESTIONS = 3

Action = Literal["create", "update", "link", "unchanged", "outdated"]
MANAGED_FIELDS = ("title", "description", "preconditions", "steps", "roles", "tags")


@dataclass
class Suggestion:
    case_id: int
    title: str
    path: str
    score: float


@dataclass
class PlanItem:
    action: Action
    key: str
    title: str
    path: list[str]
    test: CatalogTest | None = None  # None for an outdated case
    case: TestCase | None = None
    changes: list[str] = field(default_factory=list)
    note: str | None = None
    suggestions: list[Suggestion] = field(default_factory=list)


# --- Similar titles ----------------------------------------------------------------------

_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset("a an the is are be of to in on for and or with by as at it its from this that can not".split())


def _norm(title: str) -> str:
    return " ".join(_WORD.findall(title.lower()))


def _words(title: str) -> frozenset[str]:
    return frozenset(w for w in _WORD.findall(title.lower()) if w not in _STOP and len(w) > 1)


def similarity(a: str, b: str) -> float:
    """0..1: how alike two case titles read (word overlap and character sequence)."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    jaccard = len(wa & wb) / len(wa | wb)
    return round(0.5 * jaccard + 0.5 * SequenceMatcher(None, _norm(a), _norm(b)).ratio(), 3)


# --- Planning ----------------------------------------------------------------------------


def _roles(test_roles: list[str], project_roles: list[str]) -> list[str]:
    """The test's roles in the project's spelling ("Super Admin" -> "Super Admin (SA)")."""
    spelling = {role_key(r): r for r in project_roles}
    return list(dict.fromkeys(spelling.get(role_key(r), r) for r in test_roles))


def _lines(text: str) -> str:
    """Keep the test's line breaks in Markdown ("When …\nAnd …" shows as two lines)."""
    return re.sub(r" *\n", "  \n", text)


def _content(test: CatalogTest, project_roles: list[str]) -> dict[str, object]:
    return {
        "title": test.title,
        "description": test.description,
        "preconditions": test.preconditions,
        "steps": [{"action": _lines(s.action), "expected": _lines(s.expected)} for s in test.steps],
        "roles": _roles(test.roles, project_roles),
        "tags": list(dict.fromkeys(test.tags)),
    }


def _changes(case: TestCase, wanted: dict[str, object]) -> list[str]:
    out = []
    for name, value in wanted.items():
        current = getattr(case, name)
        if name == "roles":
            same = sorted(map(role_key, current)) == sorted(map(role_key, value))  # type: ignore[arg-type]
        elif name == "tags":
            same = sorted(current) == sorted(value)  # type: ignore[type-var]
        else:
            same = current == value
        if not same:
            out.append(name)
    return out


async def plan_sync(session: AsyncSession, project_id: int, tests: list[CatalogTest]) -> list[PlanItem]:
    project = await session.get(Project, project_id)
    assert project is not None
    cases = list(await session.scalars(select(TestCase).where(TestCase.project_id == project_id)))
    by_id = {c.id: c for c in cases}
    by_key = {c.automation_key: c for c in cases if c.automation_key}
    keys = {t.key for t in tests}
    items: list[PlanItem] = []
    claimed: set[int] = set()  # cases some test of the catalog belongs to

    for t in tests:
        tagged = next((by_id[i] for i in t.case_ids if i in by_id), None)
        case = tagged or by_key.get(t.key)
        item = PlanItem(action="create", key=t.key, title=t.title, path=t.path, test=t, case=case)
        items.append(item)
        if case is None:
            continue
        claimed.add(case.id)
        if case.catalog_managed:
            item.changes = _changes(case, _content(t, project.roles))
            if case.automation_key != t.key:
                item.changes.append("automation_key")
            if case.state == CaseState.outdated:
                item.changes.append("state")
            item.action = "update" if item.changes else "unchanged"
        else:
            if case.automation_key != t.key:
                item.changes.append("automation_key")
            if case.automation_status != AutomationStatus.automated:
                item.changes.append("automation_status")
            item.action = "link" if item.changes else "unchanged"
        holder = by_key.get(t.key)
        if holder is not None and holder.id != case.id:
            item.note = f"The key moves here from C{holder.id}, tagged cases win"
        if missing := [i for i in t.case_ids if i not in by_id]:
            item.note = f"Tagged with {', '.join(f'C{i}' for i in missing)}, not in this project"

    for c in cases:
        if c.catalog_managed and c.id not in claimed and c.automation_key not in keys and c.state != CaseState.outdated:
            items.append(PlanItem(action="outdated", key=c.automation_key or "", title=c.title, path=[], case=c,
                                  changes=["state"], note="Its test is no longer in the catalog"))

    # Suggestions for new tests: manual cases not linked to any test of the catalog yet.
    candidates = [c for c in cases if not c.catalog_managed and c.id not in claimed
                  and (not c.automation_key or c.automation_key not in keys)]
    if candidates and any(i.action == "create" for i in items):
        paths = await _paths(session, {c.suite_id for c in candidates})
        words = {c.id: _words(c.title) for c in candidates}
        for item in items:
            if item.action != "create":
                continue
            mine = _words(item.title)
            scored = []
            for c in candidates:
                if not (mine & words[c.id]):
                    continue
                score = similarity(item.title, c.title)
                if score >= SUGGESTION_MIN_SCORE:
                    scored.append(Suggestion(c.id, c.title, paths.get(c.section_id, ""), score))
            item.suggestions = sorted(scored, key=lambda s: (-s.score, s.case_id))[:MAX_SUGGESTIONS]
    return items


async def _paths(session: AsyncSession, suite_ids: set[int]) -> dict[int, str]:
    """section id -> "Suite > Section > Sub" for the given suites."""
    suites = {s.id: s.name for s in await session.scalars(select(Suite).where(Suite.id.in_(suite_ids)))}
    sections = list(await session.scalars(select(Section).where(Section.suite_id.in_(suite_ids))))
    paths = section_paths(sections)
    by_id = {s.id: s for s in sections}
    return {sid: f"{suites[by_id[sid].suite_id]} > {p}" for sid, p in paths.items()}


# --- Applying ----------------------------------------------------------------------------


class SyncError(ValueError):
    pass


async def _section(session: AsyncSession, suite: Suite, path: list[str], cache: dict[tuple[str, ...], Section]) -> Section:
    """The section at `path` in the suite, created (with its parents) when missing."""
    names = tuple(path) or (NO_PATH_SECTION,)
    parent: Section | None = None
    for depth in range(1, len(names) + 1):
        sub = names[:depth]
        if sub not in cache:
            found = await session.scalar(
                select(Section).where(
                    Section.suite_id == suite.id,
                    Section.name == sub[-1],
                    Section.parent_id == parent.id if parent else Section.parent_id.is_(None),
                ).order_by(Section.position, Section.id).limit(1)
            )
            if found is None:
                found = Section(suite_id=suite.id, parent_id=parent.id if parent else None, name=sub[-1][:200])
                session.add(found)
                await session.flush()
            cache[sub] = found
        parent = cache[sub]
    assert parent is not None
    return parent


async def apply_sync(
    session: AsyncSession, project_id: int, tests: list[CatalogTest], *,
    links: dict[str, int], skip: set[str], user_name: str | None,
) -> dict[str, int]:
    """Apply the plan. `links`: test key -> existing case to link instead of creating a case."""
    project = await session.get(Project, project_id)
    assert project is not None
    items = await plan_sync(session, project_id, tests)
    creatable = {i.key for i in items if i.action == "create"}
    for key in links:
        if key not in creatable:
            raise SyncError(f"{key}: only a new test can be linked to an existing case")
    if len(set(links.values())) != len(links):
        raise SyncError("Two tests are linked to the same case")
    targets = {c.id: c for c in await session.scalars(
        select(TestCase).where(TestCase.project_id == project_id, TestCase.id.in_(list(links.values())))
    )} if links else {}
    keys = {t.key for t in tests}
    for key, case_id in links.items():
        case = targets.get(case_id)
        if case is None:
            raise SyncError(f"C{case_id} is not a case of this project")
        if case.catalog_managed:
            raise SyncError(f"C{case_id} was created from the catalog; link new tests to manual cases only")
        if case.automation_key and case.automation_key in keys and case.automation_key != key:
            raise SyncError(f"C{case_id} is already linked to the test {case.automation_key}")

    counts = {"created": 0, "updated": 0, "linked": 0, "outdated": 0, "skipped": 0}
    # Keys that move to another case are released first (automation_key is unique per project).
    moving = []
    for i in items:
        if i.key in skip or i.action not in ("update", "link") or i.case is None:
            continue
        if "automation_key" in i.changes:
            moving.append(i.key)
    linked_keys = list(links)
    holders = list(await session.scalars(select(TestCase).where(
        TestCase.project_id == project_id, TestCase.automation_key.in_(moving + linked_keys)
    ))) if moving or linked_keys else []
    for h in holders:
        h.automation_key = None
        if h.catalog_managed:  # its test now belongs to another case
            h.state = CaseState.outdated
            counts["outdated"] += 1
    await session.flush()

    suite: Suite | None = None
    sections: dict[tuple[str, ...], Section] = {}
    used_roles: list[str] = []
    for i in items:
        if i.key in skip and i.action != "outdated":
            counts["skipped"] += 1
            continue
        if i.action == "outdated":
            assert i.case is not None
            i.case.state = CaseState.outdated
            i.case.updated_by = user_name
            counts["outdated"] += 1
            continue
        if i.action == "unchanged":
            continue
        assert i.test is not None
        content = _content(i.test, project.roles)
        if i.action == "create" and i.key in links:
            case = targets[links[i.key]]
            case.automation_key = i.key
            case.automation_status = AutomationStatus.automated
            case.updated_by = user_name
            counts["linked"] += 1
        elif i.action == "create":
            if suite is None:
                suite = await session.scalar(
                    select(Suite).where(Suite.project_id == project_id, Suite.name == AUTOTESTS_SUITE).limit(1)
                )
                if suite is None:
                    suite = Suite(project_id=project_id, name=AUTOTESTS_SUITE,
                                  description="Cases of the automated tests, kept in sync with them.")
                    session.add(suite)
                    await session.flush()
            section = await _section(session, suite, i.test.path, sections)
            tags = i.test.tags
            case_type = CaseType.smoke if "smoke" in tags else CaseType.regression if "regression" in tags \
                else CaseType.functional
            session.add(TestCase(
                project_id=project_id, suite_id=suite.id, section_id=section.id,
                position=await next_case_position(session, section.id),
                type=case_type, automation_status=AutomationStatus.automated, automation_key=i.key,
                state=CaseState.active, catalog_managed=True, updated_by=user_name, **content,
            ))
            await session.flush()
            used_roles += content["roles"]  # type: ignore[arg-type]
            counts["created"] += 1
        else:
            case = i.case
            assert case is not None
            if case.catalog_managed:
                for name in MANAGED_FIELDS:
                    setattr(case, name, content[name])
                used_roles += content["roles"]  # type: ignore[arg-type]
                if case.state == CaseState.outdated:
                    case.state = CaseState.active
                counts["updated"] += 1
            else:
                counts["linked"] += 1
            case.automation_key = i.key
            case.automation_status = AutomationStatus.automated
            case.updated_by = user_name
    await session.flush()
    await remember_roles(session, project_id, used_roles)
    return counts
