"""Database models.

Enums are stored as VARCHAR + CHECK constraint (not native Postgres enums) so adding
a value later is a trivial migration.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    # Fetch server-generated values (timestamps) via RETURNING on INSERT *and* UPDATE,
    # so objects stay usable after commit without lazy loads (which async forbids).
    __mapper_args__ = {"eager_defaults": True}

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


# --- Enums ---------------------------------------------------------------------------


class Priority(enum.StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class CaseType(enum.StrEnum):
    functional = "functional"
    regression = "regression"
    smoke = "smoke"
    acceptance = "acceptance"
    performance = "performance"
    security = "security"
    other = "other"


class AutomationStatus(enum.StrEnum):
    manual = "manual"
    automated = "automated"
    to_be_automated = "to_be_automated"


class RunSource(enum.StrEnum):
    manual = "manual"
    ci = "ci"


class Role(enum.StrEnum):
    admin = "admin"
    tester = "tester"


class InvitePurpose(enum.StrEnum):
    invite = "invite"  # create a new account
    reset = "reset"  # set a new password for an existing account


class ResultStatus(enum.StrEnum):
    passed = "passed"
    failed = "failed"
    blocked = "blocked"
    skipped = "skipped"
    retest = "retest"
    untested = "untested"


def _enum(e: type[enum.StrEnum], name: str) -> Enum:
    return Enum(
        e,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda cls: [m.value for m in cls],
        validate_strings=True,
    )


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _updated() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --- Tables --------------------------------------------------------------------------


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated()

    suites: Mapped[list[Suite]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class Suite(Base):
    __tablename__ = "suites"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated()

    project: Mapped[Project] = relationship(back_populates="suites")


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    suite_id: Mapped[int] = mapped_column(ForeignKey("suites.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated()


class TestCase(Base):
    __tablename__ = "test_cases"
    __test__ = False  # keep pytest from collecting this class
    __table_args__ = (
        UniqueConstraint("project_id", "automation_key", name="uq_test_cases_project_automation_key"),
        Index("ix_test_cases_tags", "tags", postgresql_using="gin"),
        Index("ix_test_cases_section_position", "section_id", "position"),
        Index("ix_test_cases_suite_external_id", "suite_id", "external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # project_id / suite_id are denormalized from the section for cheap filtering.
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    suite_id: Mapped[int] = mapped_column(ForeignKey("suites.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(500))
    preconditions: Mapped[str] = mapped_column(Text, default="", server_default="")
    # [{"action": str, "expected": str}, ...]
    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    expected_result: Mapped[str] = mapped_column(Text, default="", server_default="")
    priority: Mapped[Priority] = mapped_column(
        _enum(Priority, "priority"), default=Priority.medium, server_default=Priority.medium.value
    )
    type: Mapped[CaseType] = mapped_column(
        _enum(CaseType, "case_type"), default=CaseType.functional, server_default=CaseType.functional.value
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), default=list, server_default=text("'{}'::varchar[]")
    )
    automation_status: Mapped[AutomationStatus] = mapped_column(
        _enum(AutomationStatus, "automation_status"),
        default=AutomationStatus.manual,
        server_default=AutomationStatus.manual.value,
    )
    automation_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Id in the tool the case was imported from (e.g. "TC-770" from BrowserStack); re-imports
    # update the case instead of duplicating it.
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated()

    @property
    def key(self) -> str:
        return f"C{self.id}"


class TestRun(Base):
    __tablename__ = "test_runs"
    __test__ = False

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    source: Mapped[RunSource] = mapped_column(
        _enum(RunSource, "run_source"), default=RunSource.manual, server_default=RunSource.manual.value
    )
    branch: Mapped[str | None] = mapped_column(String(300), nullable=True)
    commit: Mapped[str | None] = mapped_column(String(100), nullable=True)
    build_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    closed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated()

    created_by: Mapped[User | None] = relationship(lazy="joined")

    @property
    def created_by_name(self) -> str | None:
        return self.created_by.name if self.created_by else None


class RunCase(Base):
    """Membership of a case in a run, with the cached latest status."""

    __tablename__ = "run_cases"

    run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id", ondelete="CASCADE"), primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    status: Mapped[ResultStatus] = mapped_column(
        _enum(ResultStatus, "result_status"),
        default=ResultStatus.untested,
        server_default=ResultStatus.untested.value,
    )
    updated_at: Mapped[datetime] = _updated()


class TestResult(Base):
    """Append-only result history. The latest result per (run, case) is the current status."""

    __tablename__ = "test_results"
    __test__ = False
    __table_args__ = (Index("ix_test_results_run_case", "run_id", "case_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id", ondelete="CASCADE"))
    case_id: Mapped[int] = mapped_column(ForeignKey("test_cases.id", ondelete="CASCADE"), index=True)
    status: Mapped[ResultStatus] = mapped_column(_enum(ResultStatus, "result_status"))
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = _now()

    user: Mapped[User | None] = relationship(lazy="joined")

    @property
    def recorded_by(self) -> str | None:
        return self.user.name if self.user else None


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # First characters of the token, shown in the UI to tell tokens apart.
    prefix: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = _now()
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)  # always lowercased
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role, "role"), default=Role.tester)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Bumped to invalidate every session of the user (password change, "sign out everywhere").
    session_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated()


class Invite(Base):
    """One-time link to create an account (invite) or set a new password (reset)."""

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    purpose: Mapped[InvitePurpose] = mapped_column(_enum(InvitePurpose, "invite_purpose"))
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[Role] = mapped_column(_enum(Role, "role"))
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )  # set for password resets
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _now()
