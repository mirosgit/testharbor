"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models import AutomationStatus, CaseType, Priority


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Auth ----------------------------------------------------------------------------


class LoginIn(BaseModel):
    username: str
    password: str


class MeOut(BaseModel):
    principal: str


# --- Projects ------------------------------------------------------------------------


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class ProjectOut(ORM):
    id: int
    name: str
    description: str
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


Tags = Annotated[list[str], AfterValidator(_clean_tags)]
AutomationKey = Annotated[str | None, Field(max_length=1000), AfterValidator(_clean_key)]


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
    position: int
    created_at: datetime
    updated_at: datetime


class CaseList(BaseModel):
    items: list[CaseOut]
    total: int


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


# --- Import / export -----------------------------------------------------------------


class ImportResult(BaseModel):
    created: int = 0
    updated: int = 0
    sections_created: int = 0
    errors: list[str] = []
