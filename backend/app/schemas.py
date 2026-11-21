"""Pydantic request/response models."""

from __future__ import annotations

import re
from datetime import datetime

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models import (
    JobStatus,
    AutomationComplexity,
    AutomationProgress,
    AutomationStatus,
    CaseState,
    CaseType,
    InvitePurpose,
    Priority,
    ResultStatus,
    Role,
    RunSource,
)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def check_report_url(v: str | None) -> str | None:
    """Only http(s) links are stored (they are rendered as hrefs)."""
    if v is None or not v.strip():
        return None
    v = v.strip()
    if not re.match(r"^https?://[^\s]+$", v, re.I):
        raise ValueError("report URL must start with http:// or https://")
    return v


def check_report_link(v: str | None) -> str | None:
    """An absolute http(s) URL, or a fragment ("#?testId=…") relative to the run's report."""
    if v is None or not v.strip():
        return None
    v = v.strip()
    return v if v.startswith("#") and " " not in v else check_report_url(v)


def resolve_report_link(report_url: str | None, link: str | None) -> str | None:
    if not link:
        return None
    if link.startswith("#"):
        return report_url.split("#", 1)[0] + link if report_url else None
    return link


ReportUrl = Annotated[str | None, Field(max_length=2000), AfterValidator(check_report_url)]
ReportLink = Annotated[str | None, Field(max_length=2000), AfterValidator(check_report_link)]


# --- Auth ----------------------------------------------------------------------------


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)


class UserOut(ORM):
    id: int
    email: str
    name: str
    role: Role
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class AdminUserOut(UserOut):
    locked: bool = False


class MeOut(UserOut):
    via: str  # "session" or "token"


class SetupStatus(BaseModel):
    has_users: bool


class ProfilePatch(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: Role | None = None
    is_active: bool | None = None
    unlock: bool | None = None


class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")
    role: Role = Role.tester


class InviteOut(ORM):
    id: int
    purpose: InvitePurpose
    email: str
    role: Role
    expires_at: datetime
    created_at: datetime


class InviteLink(InviteOut):
    token: str  # shown once; the link is /invite/<token>
    path: str


class InviteInfo(BaseModel):
    """Public info shown on the accept page."""

    purpose: InvitePurpose
    email: str
    role: Role
    name: str | None = None  # existing name for password resets
    expires_at: datetime


class InviteAccept(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    password: str = Field(max_length=256)


_ROLE_ABBR = re.compile(r"^(?P<base>.*\S)\s*\((?P<abbr>[A-Z][A-Za-z]{0,5})\)$")


def _abbreviates(abbr: str, name: str) -> bool:
    """"SA" for "Super Admin", "PdM" for "Product Manager": same first letter, and the
    abbreviation's letters appear in the name in order."""
    letters = [c for c in name.lower() if c.isalnum()]
    if not letters or abbr[0].lower() != letters[0]:
        return False
    rest = iter(letters)
    return all(ch in rest for ch in abbr.lower())


def role_key(role: str) -> str:
    """Identity of a role: case-insensitive, and "Super Admin (SA)" is the same role as
    "Super Admin". Other parentheses ("Admin (read-only)") are part of the name."""
    r = " ".join(role.split())
    m = _ROLE_ABBR.match(r)
    if m and _abbreviates(m["abbr"], m["base"]):
        r = m["base"]
    return r.lower()


def preferred_role(current: str, other: str) -> str:
    """Of two spellings of one role, keep the one carrying its abbreviation, else the current."""
    def has_abbr(r: str) -> bool:
        return role_key(r) != " ".join(r.split()).lower()

    return other if has_abbr(other) and not has_abbr(current) else current


def _clean_roles(v: list[str]) -> list[str]:
    """Trim and dedupe (see role_key), keeping the first position and the fullest spelling."""
    seen: dict[str, str] = {}
    for r in v:
        r = " ".join(r.split())[:100]
        if r:
            k = role_key(r)
            seen[k] = preferred_role(seen[k], r) if k in seen else r
    return list(seen.values())


Roles = Annotated[list[str], AfterValidator(_clean_roles)]


# --- Projects ------------------------------------------------------------------------


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    roles: Roles = Field(default=[], max_length=500)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    roles: Roles | None = Field(default=None, max_length=500)


class RoleRename(BaseModel):
    old: str = Field(min_length=1, max_length=100)
    new: str = Field(min_length=1, max_length=100)


class ProjectOut(ORM):
    id: int
    name: str
    description: str
    roles: list[str]
    created_at: datetime
    updated_at: datetime
    suite_count: int = 0
    case_count: int = 0
    run_count: int = 0


# --- Suites --------------------------------------------------------------------------


class SuiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class SuitePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class SuiteOut(ORM):
    id: int
    project_id: int
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    case_count: int = 0


# --- Sections ------------------------------------------------------------------------


class SectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    parent_id: int | None = None


class SectionPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    # Moving: set parent_id (null = top level) and/or position.
    parent_id: int | None = None
    position: int | None = None


class SectionOut(ORM):
    id: int
    suite_id: int
    parent_id: int | None
    name: str
    description: str
    position: int
    case_count: int = 0  # cases directly in this section (not descendants)


# --- Cases ---------------------------------------------------------------------------


class Step(BaseModel):
    action: str = ""
    expected: str = ""


def _clean_tags(v: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for t in v:
        t = t.strip().lower()
        if t:
            seen.setdefault(t[:100], None)
    return list(seen)


def _clean_key(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


def unsafe_automation_key(v: str) -> bool:
    """An automation key that a runner could take for an option: keys reach test commands as arguments."""
    return v.startswith("-") or "\x00" in v


def _clean_automation_key(v: str | None) -> str | None:
    v = _clean_key(v)
    if v is not None and unsafe_automation_key(v):
        raise ValueError("An automation key cannot start with '-' (it would be read as an option of the test command)")
    return v


def _clean_text(v: str | None) -> str | None:
    if v is None:
        return None
    v = " ".join(v.split())
    return v or None


Tags = Annotated[list[str], AfterValidator(_clean_tags)]
Owner = Annotated[str | None, Field(max_length=200), AfterValidator(_clean_text)]
Sprint = Annotated[str | None, Field(max_length=100), AfterValidator(_clean_text)]


class CustomField(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    value: str = Field(max_length=5000)


def _clean_fields(fields: list[CustomField]) -> list[CustomField]:
    """Trim, drop empty values, reject duplicate names (case-insensitive)."""
    out: list[CustomField] = []
    seen: set[str] = set()
    for f in fields:
        name, value = " ".join(f.name.split()), f.value.strip()
        if not name or not value:
            continue
        if name.lower() in seen:
            raise ValueError(f"duplicate field {name!r}")
        seen.add(name.lower())
        out.append(CustomField(name=name, value=value))
    return out


CustomFields = Annotated[list[CustomField], AfterValidator(_clean_fields)]
AutomationKey = Annotated[str | None, Field(max_length=1000), AfterValidator(_clean_automation_key)]
ExternalId = Annotated[str | None, Field(max_length=200), AfterValidator(_clean_key)]


class CaseFields(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    preconditions: str = ""
    steps: list[Step] = []
    expected_result: str = ""
    priority: Priority = Priority.medium
    type: CaseType = CaseType.functional
    tags: Tags = []
    automation_status: AutomationStatus = AutomationStatus.manual
    automation_key: AutomationKey = None
    external_id: ExternalId = None
    state: CaseState = CaseState.active
    owner: Owner = None
    automation_complexity: AutomationComplexity | None = None
    automation_progress: AutomationProgress | None = None
    sprint: Sprint = None
    roles: Roles = []
    custom_fields: CustomFields = []


# Nullable fields a PATCH may clear by sending null.
CLEARABLE_FIELDS = ("automation_key", "external_id", "owner", "automation_complexity",
                    "automation_progress", "sprint")


class CaseIn(CaseFields):
    section_id: int


class CasePatch(BaseModel):
    section_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    preconditions: str | None = None
    steps: list[Step] | None = None
    expected_result: str | None = None
    priority: Priority | None = None
    type: CaseType | None = None
    tags: Tags | None = None
    automation_status: AutomationStatus | None = None
    automation_key: AutomationKey = None
    external_id: ExternalId = None
    state: CaseState | None = None
    owner: Owner = None
    automation_complexity: AutomationComplexity | None = None
    automation_progress: AutomationProgress | None = None
    sprint: Sprint = None
    roles: Roles | None = None
    custom_fields: CustomFields | None = None


class CaseOut(ORM):
    id: int
    key: str
    project_id: int
    suite_id: int
    section_id: int
    title: str
    description: str
    preconditions: str
    steps: list[Step]
    expected_result: str
    priority: Priority
    type: CaseType
    tags: list[str]
    automation_status: AutomationStatus
    automation_key: str | None
    catalog_managed: bool = False  # created from the autotests' catalog: follows its test
    external_id: str | None
    state: CaseState
    owner: str | None
    automation_complexity: AutomationComplexity | None
    automation_progress: AutomationProgress | None
    sprint: str | None
    roles: list[str]
    custom_fields: list[CustomField]
    position: int
    created_at: datetime
    updated_at: datetime
    updated_by: str | None


class CaseList(BaseModel):
    items: list[CaseOut]
    total: int


class CaseBulkSet(BaseModel):
    """Fields to overwrite on every case. Omitted = unchanged; null clears optional fields."""

    priority: Priority | None = None
    type: CaseType | None = None
    automation_status: AutomationStatus | None = None
    state: CaseState | None = None
    owner: Owner = None
    sprint: Sprint = None
    automation_complexity: AutomationComplexity | None = None
    automation_progress: AutomationProgress | None = None


class CaseBulkUpdate(BaseModel):
    case_ids: list[int] = Field(min_length=1, max_length=5000)
    set: CaseBulkSet = CaseBulkSet()
    add_tags: Tags = []
    remove_tags: Tags = []
    add_roles: Roles = []
    remove_roles: Roles = []


class BulkResult(BaseModel):
    updated: int


class CaseMoveIn(BaseModel):
    case_ids: list[int] = Field(min_length=1)
    section_id: int
    # Index in the target section to insert at; None = append to the end.
    position: int | None = None


class CaseFilter(BaseModel):
    """Search/filter used by the case list and by 'create run from filter'."""

    suite_id: int | None = None
    section_id: int | None = None
    include_subsections: bool = True
    q: str | None = None
    tags: list[str] = []
    priority: list[Priority] = []
    type: list[CaseType] = []
    automation_status: list[AutomationStatus] = []
    state: list[CaseState] = []
    automation_complexity: list[AutomationComplexity] = []
    automation_progress: list[AutomationProgress] = []
    owner: list[str] = []  # any of
    sprint: list[str] = []  # any of
    roles: list[str] = []  # cases with any of these roles
    # Custom field name -> accepted values (any of them); several names must all match.
    fields: dict[str, list[str]] = {}


class FieldValues(BaseModel):
    name: str
    values: list[str]


class CaseValues(BaseModel):
    """Values in use in a project, for autocomplete and filters."""

    owners: list[str]  # case owners plus active users' names
    sprints: list[str]
    roles: list[str]


# --- Import / export -----------------------------------------------------------------


class ExtraColumn(BaseModel):
    name: str
    selected: bool  # imported as a custom field


class ImportResult(BaseModel):
    created: int = 0
    updated: int = 0
    sections_created: int = 0
    errors: list[str] = []  # rows that were skipped
    warnings: list[str] = []  # rows imported with a value we couldn't map
    ignored_columns: list[str] = []  # columns with data that were not imported
    extra_columns: list[ExtraColumn] = []  # columns that can become custom fields
    dry_run: bool = False
    section_id: int | None = None  # section the import went into (if one was chosen)


# --- Runs ----------------------------------------------------------------------------


class RunSelection(BaseModel):
    """Which cases to include. All given selectors are combined (union)."""

    case_ids: list[int] = []
    suite_id: int | None = None
    section_ids: list[int] = []
    filter: CaseFilter | None = None


class RunIn(RunSelection):
    name: str = Field(min_length=1, max_length=300)
    description: str = ""


class RunPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    report_url: ReportUrl = None  # "" or null clears it
    closed: bool | None = None


class RunStats(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    blocked: int = 0
    skipped: int = 0
    retest: int = 0
    untested: int = 0


class RunOut(ORM):
    id: int
    project_id: int
    name: str
    description: str
    source: RunSource
    branch: str | None
    commit: str | None
    build_url: str | None
    report_url: str | None = None
    closed: bool
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by_name: str | None = None
    stats: RunStats = RunStats()


class RunList(BaseModel):
    items: list[RunOut]
    total: int


class RunsDelete(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)


class RunsDeleted(BaseModel):
    deleted: int


class ResultIn(BaseModel):
    case_id: int
    status: ResultStatus
    comment: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    error_message: str | None = None
    stack_trace: str | None = None
    report_link: ReportLink = None
    config: str | None = Field(default=None, max_length=200)  # e.g. a role or a browser the test ran in


class BulkResultsIn(BaseModel):
    results: list[ResultIn] = Field(min_length=1, max_length=5000)


class ResultOut(ORM):
    id: int
    run_id: int
    case_id: int
    status: ResultStatus
    comment: str | None
    duration_ms: int | None
    error_message: str | None
    stack_trace: str | None
    recorded_by: str | None = None
    config: str | None = None
    # Resolved against the run's report URL; null when there is nothing to open.
    report_link: str | None = None
    created_at: datetime


class RunCaseOut(BaseModel):
    case_id: int
    key: str
    title: str
    priority: Priority
    automation_status: AutomationStatus
    suite_id: int
    section_id: int
    section_path: str
    status: ResultStatus
    result_count: int
    last_result: ResultOut | None


class CaseHistoryItem(BaseModel):
    run_id: int
    run_name: str
    run_source: RunSource
    run_closed: bool
    run_created_at: datetime
    branch: str | None
    status: ResultStatus
    result_count: int
    last_result: ResultOut | None


# --- Automation ----------------------------------------------------------------------


class UnmatchedTest(BaseModel):
    name: str
    classname: str
    reason: str


class JUnitImportResult(BaseModel):
    run_id: int
    run_name: str
    total: int  # <testcase> elements in the uploaded files
    matched: int  # tests mapped to existing cases
    created: int  # cases auto-created
    unmatched: list[UnmatchedTest]
    statuses: dict[str, int]  # results recorded, by status


class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TokenOut(ORM):
    id: int
    user_id: int
    owner: str | None = None  # owner's name (shown to admins)
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class TokenCreated(TokenOut):
    token: str  # shown only once


# --- Automation jobs (run tests from TestHarbor via an agent) ---------------------------


OPTION_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
ParamValue = str | bool | list[str]


def check_params(params: dict[str, ParamValue]) -> dict[str, ParamValue]:
    """Run options are plain values: the agent checks them against its own list of options."""
    if len(params) > 50:
        raise ValueError("At most 50 run options")
    for name, value in params.items():
        if not OPTION_NAME.match(name):
            raise ValueError(f"Invalid run option name {name!r} (expected e.g. ENV or ROLES)")
        values = value if isinstance(value, list) else [] if isinstance(value, bool) else [value]
        if len(values) > 500 or any(len(v) > 200 for v in values):
            raise ValueError(f"Run option {name}: too many or too long values")
    return params


BRANCH_NAME = re.compile(r"^(?!-)(?!.*\.\.)(?!.*//)[A-Za-z0-9._/@+-]{1,255}(?<![./])$")


def check_branch(value: str | None) -> str | None:
    """A plain git branch name (the agent passes it to git as an argument, never to a shell)."""
    if value is None or value == "":
        return None
    if not BRANCH_NAME.match(value) or value.endswith(".lock"):
        raise ValueError(f"Invalid branch name {value!r}")
    return value


class AgentChoice(BaseModel):
    value: str = Field(max_length=200)
    label: str = Field(default="", max_length=200)


class AgentOption(BaseModel):
    """One run option an agent offers (from its --options file): an environment variable of its command."""

    name: Annotated[str, Field(pattern=OPTION_NAME.pattern)]
    label: str = Field(default="", max_length=100)
    type: Literal["choice", "multi", "bool"]
    choices: list[AgentChoice] = Field(default=[], max_length=500)
    default: ParamValue | None = None
    hint: str | None = Field(default=None, max_length=300)


class JobIn(BaseModel):
    """Start automated tests. Without run_id a new CI run is created for the results."""

    run_id: int | None = None
    name: str | None = Field(default=None, max_length=300)  # new run's name
    case_ids: list[int] = Field(default=[], max_length=5000)  # only these cases; empty = all tests
    only_failed: bool = False  # with run_id: the run's failed cases
    params: Annotated[dict[str, ParamValue], AfterValidator(check_params)] = {}  # run options of the agent
    agent: str | None = Field(default=None, max_length=200)  # only this agent may take it
    branch: Annotated[str | None, AfterValidator(check_branch)] = None  # for a server agent


class CatalogTest(BaseModel):
    """One automated test as an agent reports it (`testcli agent --catalog`)."""

    # stable id; reports carry it as automation_key
    key: Annotated[str, Field(min_length=1, max_length=1000), AfterValidator(_clean_automation_key)]
    title: str = Field(min_length=1, max_length=500)
    path: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(default=[], max_length=10)
    description: str = Field(default="", max_length=50_000)
    preconditions: str = Field(default="", max_length=50_000)
    steps: list[Step] = Field(default=[], max_length=300)
    # The outcome of the whole test; when not given, the expected result of the last step.
    expected_result: str | None = Field(default=None, max_length=50_000)
    roles: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(default=[], max_length=200)
    tags: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(default=[], max_length=50)
    case_ids: list[int] = Field(default=[], max_length=50)  # cases the test is tagged with


def _unique_keys(tests: list[CatalogTest]) -> list[CatalogTest]:
    seen: set[str] = set()
    for t in tests:
        if t.key in seen:
            raise ValueError(f"Test key listed twice: {t.key}")
        seen.add(t.key)
    return tests


class CatalogIn(BaseModel):
    agent: str | None = Field(default=None, max_length=200)
    tests: Annotated[list[CatalogTest], AfterValidator(_unique_keys)] = Field(max_length=20_000)


class CatalogSuggestionOut(BaseModel):
    case_id: int
    key: str
    title: str
    path: str
    score: float


class CatalogItemOut(BaseModel):
    action: Literal["create", "update", "link", "unchanged", "outdated"]
    key: str
    title: str
    path: list[str]
    case_id: int | None = None
    case_key: str | None = None
    case_title: str | None = None
    changes: list[str] = []
    note: str | None = None
    suggestions: list[CatalogSuggestionOut] = []


class CatalogPreview(BaseModel):
    agent: str | None
    uploaded_at: datetime
    suite: str  # where new cases go
    counts: dict[str, int]  # per action
    items: list[CatalogItemOut]


class CatalogApply(BaseModel):
    uploaded_at: datetime  # the catalog the preview showed; 409 if a newer one arrived since
    links: dict[str, int] = {}  # test key -> existing case to link instead of creating a case
    skip: list[str] = Field(default=[], max_length=20_000)  # test keys to leave alone this time


class CatalogApplied(BaseModel):
    created: int
    updated: int
    linked: int
    outdated: int
    skipped: int


class JobOut(ORM):
    id: int
    project_id: int
    run_id: int
    status: JobStatus
    case_ids: list[int]
    params: dict[str, ParamValue] = {}
    target_agent: str | None = None
    branch: str | None = None
    # Only in the answer to an agent's claim: automation keys of the job's cases, so a runner can
    # select tests by them (the ids are in case_ids).
    automation_keys: list[str] = []
    agent: str | None
    exit_code: int | None
    message: str | None
    requested_by_name: str | None = None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobDetail(JobOut):
    log: str


class AgentInfo(BaseModel):
    """Where an agent runs the tests from, shown next to its name."""

    mode: Literal["local", "repo"] | None = None
    folder: str | None = Field(default=None, max_length=500)
    branch: str | None = Field(default=None, max_length=300)
    commit: str | None = Field(default=None, max_length=64)
    dirty: bool | None = None  # uncommitted changes in a local folder
    framework: str | None = Field(default=None, max_length=50)
    # A server agent ("repo"): the repository (no credentials) and its branches to pick from.
    repo: str | None = Field(default=None, max_length=500)
    default_branch: str | None = Field(default=None, max_length=255)
    branches: list[Annotated[str, Field(max_length=255)]] = Field(default=[], max_length=2000)


class AgentClaim(BaseModel):
    agent: str = Field(min_length=1, max_length=200)
    options: list[AgentOption] = Field(default=[], max_length=50)  # what the agent can be asked to vary
    info: AgentInfo = Field(default_factory=lambda: AgentInfo())


class JobProgress(BaseModel):
    log: str = Field(default="", max_length=1_000_000)  # new output since the last call


class JobFinish(JobProgress):
    status: Literal["finished", "error"]
    exit_code: int | None = None
    message: str | None = Field(default=None, max_length=5000)


class JobControl(BaseModel):
    cancelled: bool  # the agent should stop the tests


class AgentOut(BaseModel):
    name: str
    last_seen_at: datetime
    online: bool
    options: list[AgentOption] = []
    info: AgentInfo = Field(default_factory=lambda: AgentInfo())

