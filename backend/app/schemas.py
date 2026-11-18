"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models import (
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


def _clean_roles(v: list[str]) -> list[str]:
    """Trim and dedupe case-insensitively, keeping the first spelling."""
    seen: dict[str, str] = {}
    for r in v:
        r = " ".join(r.split())[:100]
        if r:
            seen.setdefault(r.lower(), r)
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
AutomationKey = Annotated[str | None, Field(max_length=1000), AfterValidator(_clean_key)]
ExternalId = Annotated[str | None, Field(max_length=200), AfterValidator(_clean_key)]


class CaseFields(BaseModel):
    title: str = Field(min_length=1, max_length=500)
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
    preconditions: str
    steps: list[Step]
    expected_result: str
    priority: Priority
    type: CaseType
    tags: list[str]
    automation_status: AutomationStatus
    automation_key: str | None
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
    closed: bool
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by_name: str | None = None
    stats: RunStats = RunStats()


class RunList(BaseModel):
    items: list[RunOut]
    total: int


class ResultIn(BaseModel):
    case_id: int
    status: ResultStatus
    comment: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    error_message: str | None = None
    stack_trace: str | None = None


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
