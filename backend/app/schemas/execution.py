import uuid
from typing import Optional, List, Any
from pydantic import BaseModel
from app.models.entities import VerdictEnum

# 1. RUN REQUEST
class RunCodeRequest(BaseModel):
    language:str
    code:str
    # If the custom input is None, run against the sample test cases
    custom_input: Optional[str] = None

class TestCaseRunResult(BaseModel):
    test_case_id: Optional[uuid.UUID] = None
    input: str
    expected_output: Optional[str] = None
    actual_output: Optional[str] = None
    passed: bool
    runtime_ms: int
    stderr: str = ""
    error: Optional[str] = None

class RunCodeResponse(BaseModel):
    all_passed: bool
    results: List[TestCaseRunResult]

# 2. SUBMIT REQUEST (Graded Run)
class SubmitCodeRequest(BaseModel):
    user_id: uuid.UUID
    language: str
    code: str

class SubmitCodeResponse(BaseModel):
    submission_id: uuid.UUID
    verdict: VerdictEnum
    passed_test_cases: int
    total_test_cases: int
    runtime_ms: Optional[int]
    memory_kb:Optional[int]
    failed_test_case: Optional[dict[str, Any]] = None
    error_output: Optional[str] = None
