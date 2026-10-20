import enum
import uuid
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# --- ENUMS ---
class DifficultyEnum(str, enum.Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class ProblemStatusEnum(str, enum.Enum):
    ATTEMPTED = "ATTEMPTED"
    SOLVED = "SOLVED"


class VerdictEnum(str, enum.Enum):
    PENDING = "PENDING"
    AC = "AC"    # Accepted
    WA = "WA"    # Wrong Answer
    TLE = "TLE"  # Time Limit Exceeded
    MLE = "MLE"  # Memory Limit Exceeded
    RE = "RE"    # Runtime Error
    CE = "CE"    # Compilation Error


# --- 1. USERS TABLE ---
class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    about: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    problem_statuses: Mapped[List["UserProblemStatus"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    drafts: Mapped[List["UserDraft"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    submissions: Mapped[List["Submission"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


# --- 2. PROBLEMS TABLE ---
class Problem(Base):
    __tablename__ = "problems"

    problem_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    difficulty: Mapped[DifficultyEnum] = mapped_column(
        Enum(DifficultyEnum, name="difficulty_enum"), nullable=False
    )
    prob_description: Mapped[str] = mapped_column(Text, nullable=False)
    prob_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    prob_examples: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    prob_constraints: Mapped[str] = mapped_column(Text, nullable=False)
    time_limit_ms: Mapped[int] = mapped_column(Integer, default=2000, nullable=False)
    memory_limit_kb: Mapped[int] = mapped_column(Integer, default=262144, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    language_templates: Mapped[List["LanguageTemplate"]] = relationship(
        back_populates="problem", cascade="all, delete-orphan"
    )
    test_cases: Mapped[List["TestCase"]] = relationship(
        back_populates="problem", cascade="all, delete-orphan", order_by="TestCase.ordinal_order"
    )


# --- 3. LANGUAGE TEMPLATE TABLE (Composite PK) ---
class LanguageTemplate(Base):
    __tablename__ = "language_template"

    problem_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("problems.problem_id", ondelete="CASCADE"),
        primary_key=True,
    )
    template_language: Mapped[str] = mapped_column(String(30), primary_key=True)
    boilerplate: Mapped[str] = mapped_column(Text, nullable=False)
    driver_harness: Mapped[str] = mapped_column(Text, nullable=False)

    problem: Mapped["Problem"] = relationship(back_populates="language_templates")


# --- 4. TEST CASES TABLE ---
class TestCase(Base):
    __tablename__ = "test_cases"

    test_case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("problems.problem_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expected_input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_output: Mapped[str] = mapped_column(Text, nullable=False)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ordinal_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    problem: Mapped["Problem"] = relationship(back_populates="test_cases")


# --- 5. USER PROBLEM STATUS TABLE (Composite PK) ---
class UserProblemStatus(Base):
    __tablename__ = "user_problem_status"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("problems.problem_id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[Optional[ProblemStatusEnum]] = mapped_column(
        Enum(ProblemStatusEnum, name="problem_status_enum"), nullable=True
    )
    is_favourite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    solve_again: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="problem_statuses")
    problem: Mapped["Problem"] = relationship()


# --- 6. USER DRAFT TABLE (Composite PK for Continuous Auto-Save) ---
class UserDraft(Base):
    __tablename__ = "user_draft"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("problems.problem_id", ondelete="CASCADE"),
        primary_key=True,
    )
    language: Mapped[str] = mapped_column(String(30), primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="drafts")
    problem: Mapped["Problem"] = relationship()


# --- 7. SUBMISSIONS TABLE (Immutable Graded Runs) ---
class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        Index("ix_submissions_user_problem_created", "user_id", "problem_id", "created_at"),
    )

    sub_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("problems.problem_id", ondelete="CASCADE"),
        nullable=False,
    )
    language: Mapped[str] = mapped_column(String(30), nullable=False)
    submitted_code: Mapped[str] = mapped_column(Text, nullable=False)
    result_verdict: Mapped[VerdictEnum] = mapped_column(
        Enum(VerdictEnum, name="verdict_enum"), default=VerdictEnum.PENDING, nullable=False
    )
    runtime_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    memory_kb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="submissions")
    problem: Mapped["Problem"] = relationship()