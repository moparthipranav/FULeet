import uuid
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict
from app.models.entities import DifficultyEnum, ProblemStatusEnum, VerdictEnum

# Create or SEED schemas
class LanguageTemplateCreate(BaseModel):
    template_language:str
    boilerplate:str
    driver_harness:str

class TestCaseCreate(BaseModel):
    expected_input: str
    expected_output: str
    is_sample: bool = False
    ordinal_order: int = 1

class ProblemCreate(BaseModel):
    slug: str
    title: str
    difficulty: DifficultyEnum
    prob_description: str
    prob_image_url: Optional[str] = None
    prob_examples: List[dict[str, Any]] = []
    prob_constraints: str
    time_limit_ms: int = 2000
    memory_limit_kb: int = 262144
    language_templates: List[LanguageTemplateCreate]
    test_cases: List[TestCaseCreate]

# --- PUBLIC READ SCHEMAS (Safe for Browser) ---
class LanguageTemplatePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    template_language: str
    boilerplate: str  # Notice: driver_harness is hidden from client!


class SampleTestCasePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    test_case_id: uuid.UUID
    expected_input: str
    expected_output: str
    ordinal_order: int


class ProblemListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    problem_id: uuid.UUID
    slug: str
    title: str
    difficulty: DifficultyEnum
    status: Optional[ProblemStatusEnum] = None
    is_favourite: bool = False
    solve_again: bool = False


class ProblemWorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    problem_id: uuid.UUID
    slug: str
    title: str
    difficulty: DifficultyEnum
    prob_description: str
    prob_image_url: Optional[str]
    prob_examples: List[dict[str, Any]]
    prob_constraints: str
    time_limit_ms: int
    memory_limit_kb: int
    language_templates: List[LanguageTemplatePublic]
    sample_test_cases: List[SampleTestCasePublic]
    saved_drafts: dict[str, str] = {}  # { "python": "user's half-solved code..." }


# --- AUTO-SAVE & BOOKMARK SCHEMAS ---
class DraftSaveRequest(BaseModel):
    user_id: uuid.UUID
    language: str
    code: str


class BookmarkToggleRequest(BaseModel):
    user_id: uuid.UUID
    is_favourite: Optional[bool] = None
    solve_again: Optional[bool] = None
