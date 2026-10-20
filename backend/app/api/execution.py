import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.entities import (
    Problem,
    ProblemStatusEnum,
    Submission,
    User,
    UserProblemStatus,
    VerdictEnum,
)

from app.sandbox.piston_runner import PistonRunner
from app.schemas.execution import (
    RunCodeRequest,
    RunCodeResponse,
    SubmitCodeRequest,
    SubmitCodeResponse,
    TestCaseRunResult,
)
from app.services.evaluator import (
    evaluate_single_test_case,
    grade_submission,
    stitch_driver,
)

router = APIRouter(prefix="/api/v1/problems/{slug}", tags=["Execution & Grading"])
piston_runner = PistonRunner()

# 1. RUN CODE (sample tests or custom input - Does not persist the submission)
@router.post("/run", response_model=RunCodeResponse)
async def run_code(
    slug:str,
    payload: RunCodeRequest,
    db: AsyncSession = Depends(get_db),
):

    stmt = (
        select(Problem)
        .where(Problem.slug == slug)
        .options(
            selectinload(Problem.language_templates),
            selectinload(Problem.test_cases)
        )
    )

    problem = await db.scalar(stmt)
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")

    template = next(
        (t for t in problem.language_templates if t.template_language == payload.language),
        None,
    )

    if not template:
        raise HTTPException(
            status_code=400,
            detail=f"Language '{payload.language}' not configured for this problem.",
        )

    full_code = stitch_driver(payload.code, template.driver_harness)
    results = []
    all_passed = True

    if payload.custom_input is not None:
        # Run against user custom input
        start_time = time.perf_counter()
        res = await piston_runner.execute(
            language=payload.language,
            source_code=full_code,
            stdin_data=payload.custom_input,
            time_limit_ms=problem.time_limit_ms,
            memory_limit_kb=problem.memory_limit_kb,
        )
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        execution_runtime = res.runtime_ms or duration_ms
        timed_out = res.timed_out or execution_runtime > problem.time_limit_ms
        results.append(
            TestCaseRunResult(
                test_case_id=None,
                input=payload.custom_input,
                expected_output=None,
                actual_output=res.stdout.strip(),
                passed=(
                    res.exit_code == 0
                    and not timed_out
                ),
                runtime_ms=execution_runtime,
                stderr=res.stderr,
                error=(
                    "Time Limit Exceeded"
                    if timed_out
                    else res.stderr if res.exit_code != 0 else None
                ),
            )
        )

        all_passed = res.exit_code == 0 and not timed_out

    else:
        # Run against the sample test cases
        sample_cases = [tc for tc in problem.test_cases if tc.is_sample]
        for tc in sample_cases:
            passed, res, err = await evaluate_single_test_case(
                language=payload.language,
                full_source_code=full_code,
                test_case=tc,
                time_limit_ms=problem.time_limit_ms,
                memory_limit_kb=problem.memory_limit_kb,
            )

            if not passed:
                all_passed = False

            results.append(
                TestCaseRunResult(
                    test_case_id=tc.test_case_id,
                    input=tc.expected_input,
                    expected_output=tc.expected_output,
                    actual_output=res.stdout.strip(),
                    passed=passed,
                    runtime_ms=res.runtime_ms,
                    stderr=res.stderr,
                    error=err,
                )
            )
    
    return RunCodeResponse(all_passed=all_passed, results=results)


# 2. SUBMIT CODE (Full grading, records submission, updates user status)
@router.post("/submit", response_model=SubmitCodeResponse)
async def submit_code(
    slug: str,
    payload: SubmitCodeRequest,
    db: AsyncSession = Depends(get_db),
):

    # Verify if the user exists
    user = await db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    stmt = (
        select(Problem)
        .where(Problem.slug == slug)
        .options(
            selectinload(Problem.language_templates),
            selectinload(Problem.test_cases),
        )
    )

    problem = await db.scalar(stmt)

    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")

    template = next(
        (t for t in problem.language_templates if t.template_language == payload.language),
        None,
    )

    if not template:
        raise HTTPException(
            status_code=400,
            detail=f"Language '{payload.language}' not configured for this problem.",
        )

    # Grade across all the test cases
    verdict, passed_count, total_count, max_runtime, failed_case, err_out = (
        await grade_submission(
            language=payload.language,
            code=payload.code,
            template=template,
            test_cases=problem.test_cases,
            time_limit_ms=problem.time_limit_ms,
            memory_limit_kb=problem.memory_limit_kb,
        )
    )

    # Insert an immutable submission record
    sub = Submission(
        user_id=payload.user_id,
        problem_id=problem.problem_id,
        language=payload.language,
        submitted_code=payload.code,
        result_verdict=verdict,
        runtime_ms=max_runtime,
        error_output=err_out,
    )

    db.add(sub)

    # Update user_problem_status
    next_status = (
        ProblemStatusEnum.SOLVED
        if verdict == VerdictEnum.AC
        else ProblemStatusEnum.ATTEMPTED
    )
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "sqlite":
        insert_status = sqlite_insert(UserProblemStatus)
    elif dialect_name == "postgresql":
        insert_status = pg_insert(UserProblemStatus)
    else:
        raise RuntimeError(f"Unsupported database dialect for upsert: {dialect_name}")

    status_upsert = insert_status.values(
        user_id=payload.user_id,
        problem_id=problem.problem_id,
        status=next_status,
        is_favourite=False,
        solve_again=False,
    )
    await db.execute(
        status_upsert.on_conflict_do_update(
            index_elements=["user_id", "problem_id"],
            set_={
                "status": case(
                    (
                        UserProblemStatus.status == ProblemStatusEnum.SOLVED,
                        UserProblemStatus.status,
                    ),
                    else_=status_upsert.excluded.status,
                )
            },
        )
    )

    await db.commit()
    await db.refresh(sub)

    return SubmitCodeResponse(
        submission_id=sub.sub_id,
        verdict=sub.result_verdict,
        passed_test_cases=passed_count,
        total_test_cases=total_count,
        runtime_ms=sub.runtime_ms,
        memory_kb=sub.memory_kb,
        failed_test_case=failed_case,
        error_output=sub.error_output,
    )
