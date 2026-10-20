import time
from typing import Optional, Tuple, List
from app.sandbox.piston_runner import PistonRunner
from app.sandbox.base import ExecutionResult
from app.models.entities import LanguageTemplate, TestCase, VerdictEnum

piston_runner = PistonRunner()

async def evaluate_single_test_case(
    language:str,
    full_source_code: str,
    test_case: TestCase,
    time_limit_ms: int,
    memory_limit_kb: int = 262144,
) -> Tuple[bool, ExecutionResult, Optional[str]]:
    
    start_time = time.perf_counter()
    res = await piston_runner.execute(
        language=language,
        source_code=full_source_code,
        stdin_data=test_case.expected_input,
        time_limit_ms=time_limit_ms,
        memory_limit_kb=memory_limit_kb,
    )
    duration_ms = int((time.perf_counter() - start_time) * 1000)
    if res.runtime_ms <= 0:
        res.runtime_ms = duration_ms

    if res.timed_out or res.runtime_ms > time_limit_ms:
        res.timed_out = True
        return False, res, "Time Limit Exceeded"
    
    if res.exit_code != 0:
        return False, res, res.stderr or "Runtime Error"

    # Normalize outputs by trimming whitespace and linebreaks
    actual = res.stdout.strip()
    expected = test_case.expected_output.strip()

    if actual != expected:
        return False, res, f"Expected '{expected}', got '{actual}'"

    return True, res, None

async def grade_submission(
    language: str,
    code: str,
    template: LanguageTemplate,
    test_cases: List[TestCase],
    time_limit_ms: int,
    memory_limit_kb: int = 262144,
) -> Tuple[VerdictEnum, int, int, int, Optional[dict], Optional[str]]:
    """
    Grades code against all test cases.
    Returns: (verdict, passed_count, total_count, max_runtime_ms, failed_case_detail, error_output)
    """

    full_source = stitch_driver(code, template.driver_harness)
    total_cases = len(test_cases)
    passed_cases = 0
    max_runtime= 0

    for tc in test_cases:
        passed, res, err = await evaluate_single_test_case(
            language=language,
            full_source_code=full_source,
            test_case=tc,
            time_limit_ms=time_limit_ms,
            memory_limit_kb=memory_limit_kb,
        )
        max_runtime = max(max_runtime, res.runtime_ms)

        if not passed:
            # Determing the failing verdict
            if res.compilation_error:
                verdict = VerdictEnum.CE
            elif res.timed_out:
                verdict = VerdictEnum.TLE
            elif res.exit_code != 0:
                verdict = VerdictEnum.RE
            else:
                verdict = VerdictEnum.WA
            
            failed_detail = {
                "input": tc.expected_input,
                "expected": tc.expected_output,
                "actual": res.stdout.strip(),
            }

            return verdict, passed_cases, total_cases, max_runtime, failed_detail, err

        passed_cases += 1
    
    return VerdictEnum.AC, passed_cases, total_cases, max_runtime, None, None

def stitch_driver(code: str, harness: str) -> str:
    """Combines user's solution with the hidden driver code."""
    return f"{code}\n\n{harness}"