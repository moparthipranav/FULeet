import uuid

import pytest
from sqlalchemy import func, select

from app.models.entities import (
    ProblemStatusEnum,
    Submission,
    User,
    UserDraft,
    UserProblemStatus,
    VerdictEnum,
)
from app.sandbox.base import ExecutionResult
from app.sandbox.piston_runner import PistonRunner

from tests.test_workspace_and_drafts import create_problem, create_user


CORRECT_CODE = "class Solution:\n    def twoSum(self, nums, target): return [0, 1]"
WRONG_CODE = "WRONG_ANSWER"


@pytest.mark.asyncio
async def test_run_executes_samples_only_and_does_not_persist(client, piston_runner, db_session):
    await create_problem(client)

    response = await client.post(
        "/api/v1/problems/two-sum/run",
        json={"language": "python", "code": CORRECT_CODE},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["all_passed"] is True
    assert len(result["results"]) == 2
    assert len(piston_runner.calls) == 2
    assert {call["stdin_data"] for call in piston_runner.calls} == {
        "[2,7,11,15]\n9",
        "[3,2,4]\n6",
    }
    assert await db_session.scalar(select(func.count()).select_from(Submission)) == 0


@pytest.mark.asyncio
async def test_run_custom_input_is_not_graded_against_an_expected_output(
    client, piston_runner
):
    await create_problem(client)

    response = await client.post(
        "/api/v1/problems/two-sum/run",
        json={
            "language": "python",
            "code": CORRECT_CODE,
            "custom_input": "[1,2]\n3",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["all_passed"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["input"] == "[1,2]\n3"
    assert result["results"][0]["expected_output"] is None
    assert result["results"][0]["passed"] is True
    assert piston_runner.calls[0]["stdin_data"] == "[1,2]\n3"


@pytest.mark.asyncio
async def test_submit_accepted_persists_snapshot_and_marks_problem_solved(
    client, db_session
):
    problem = await create_problem(client)
    user_id = await create_user(client)

    response = await client.post(
        f"/api/v1/problems/{problem['slug']}/submit",
        json={"user_id": str(user_id), "language": "python", "code": CORRECT_CODE},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["verdict"] == "AC"
    assert result["passed_test_cases"] == result["total_test_cases"] == 3
    submission = await db_session.get(Submission, uuid.UUID(result["submission_id"]))
    assert submission.submitted_code == CORRECT_CODE
    assert submission.result_verdict == VerdictEnum.AC
    assert submission.created_at is not None
    status = await db_session.scalar(select(UserProblemStatus))
    assert status.status == ProblemStatusEnum.SOLVED

    catalog = await client.get(
        "/api/v1/problems", params={"user_id": str(user_id)}
    )
    assert catalog.json()[0]["status"] == "SOLVED"


@pytest.mark.asyncio
async def test_submit_wrong_answer_records_details_and_attempted_status(
    client, db_session
):
    problem = await create_problem(client)
    user_id = await create_user(client)

    response = await client.post(
        f"/api/v1/problems/{problem['slug']}/submit",
        json={"user_id": str(user_id), "language": "python", "code": WRONG_CODE},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["verdict"] == "WA"
    assert result["failed_test_case"] == {
        "input": "[2,7,11,15]\n9",
        "expected": "[0, 1]",
        "actual": "[0, 0]",
    }
    status = await db_session.scalar(select(UserProblemStatus))
    assert status.status == ProblemStatusEnum.ATTEMPTED


@pytest.mark.asyncio
async def test_failed_submit_never_downgrades_solved_status(client, db_session):
    problem = await create_problem(client)
    user_id = await create_user(client)
    endpoint = f"/api/v1/problems/{problem['slug']}/submit"
    accepted = await client.post(
        endpoint,
        json={"user_id": str(user_id), "language": "python", "code": CORRECT_CODE},
    )
    wrong = await client.post(
        endpoint,
        json={"user_id": str(user_id), "language": "python", "code": WRONG_CODE},
    )

    assert accepted.json()["verdict"] == "AC"
    assert wrong.json()["verdict"] == "WA"
    status = await db_session.scalar(select(UserProblemStatus))
    assert status.status == ProblemStatusEnum.SOLVED


@pytest.mark.asyncio
async def test_submit_timeout_is_tle(client):
    problem = await create_problem(client)
    user_id = await create_user(client)

    response = await client.post(
        f"/api/v1/problems/{problem['slug']}/submit",
        json={
            "user_id": str(user_id),
            "language": "python",
            "code": "INFINITE_LOOP",
        },
    )

    assert response.status_code == 200
    assert response.json()["verdict"] == "TLE"


@pytest.mark.asyncio
async def test_elapsed_runtime_over_limit_is_tle(client):
    problem = await create_problem(client)
    user_id = await create_user(client)

    response = await client.post(
        f"/api/v1/problems/{problem['slug']}/submit",
        json={"user_id": str(user_id), "language": "python", "code": "SLOW"},
    )

    assert response.status_code == 200
    assert response.json()["verdict"] == "TLE"


@pytest.mark.asyncio
async def test_submit_runtime_error_contains_traceback(client):
    problem = await create_problem(client)
    user_id = await create_user(client)

    response = await client.post(
        f"/api/v1/problems/{problem['slug']}/submit",
        json={
            "user_id": str(user_id),
            "language": "python",
            "code": "ZERO_DIVISION",
        },
    )

    assert response.status_code == 200
    assert response.json()["verdict"] == "RE"
    assert "ZeroDivisionError: division by zero" in response.json()["error_output"]


@pytest.mark.asyncio
async def test_compile_error_has_ce_verdict(client):
    problem = await create_problem(client)
    user_id = await create_user(client)

    response = await client.post(
        f"/api/v1/problems/{problem['slug']}/submit",
        json={
            "user_id": str(user_id),
            "language": "python",
            "code": "COMPILATION_ERROR",
        },
    )

    assert response.status_code == 200
    assert response.json()["verdict"] == "CE"


@pytest.mark.asyncio
async def test_problem_without_requested_language_returns_400(client):
    await create_problem(client)

    response = await client.post(
        "/api/v1/problems/two-sum/run",
        json={"language": "rust", "code": "fn main() {}"},
    )

    assert response.status_code == 400
    assert "not configured" in response.json()["detail"]


@pytest.mark.asyncio
async def test_sandbox_unavailable_is_reported_as_bad_gateway(client):
    await create_problem(client)

    response = await client.post(
        "/api/v1/problems/two-sum/run",
        json={"language": "python", "code": "SANDBOX_UNAVAILABLE"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Piston execution service is unavailable"


@pytest.mark.asyncio
async def test_user_delete_cascades_to_status_drafts_and_submissions(
    client, db_session
):
    problem = await create_problem(client)
    user_id = await create_user(client)
    await client.put(
        f"/api/v1/problems/{problem['slug']}/draft",
        json={"user_id": str(user_id), "language": "python", "code": CORRECT_CODE},
    )
    await client.patch(
        f"/api/v1/problems/{problem['slug']}/bookmark",
        json={"user_id": str(user_id), "is_favourite": True},
    )
    await client.post(
        f"/api/v1/problems/{problem['slug']}/submit",
        json={"user_id": str(user_id), "language": "python", "code": CORRECT_CODE},
    )
    user = await db_session.get(User, user_id)

    await db_session.delete(user)
    await db_session.commit()

    assert await db_session.scalar(select(func.count()).select_from(UserDraft)) == 0
    assert await db_session.scalar(select(func.count()).select_from(UserProblemStatus)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Submission)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("signal", ["SIGKILL", "SIGXCPU"])
async def test_piston_runner_sends_limits_and_maps_termination_signals(
    monkeypatch, signal
):
    request_body = {}
    client_timeout = None
    client_closed = False

    class MockResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "run": {
                    "stdout": "",
                    "stderr": "CPU time limit exceeded",
                    "code": 1,
                    "signal": signal,
                    "time": 1.2,
                    "memory": 2048,
                }
            }

    class MockAsyncClient:
        def __init__(self, timeout):
            nonlocal client_timeout
            client_timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            nonlocal client_closed
            client_closed = True
            return None

        async def post(self, _url, json):
            request_body.update(json)
            return MockResponse()

    monkeypatch.setattr("app.sandbox.piston_runner.httpx.AsyncClient", MockAsyncClient)
    runner = PistonRunner("http://piston.test/execute")

    result = await runner.execute(
        language="python",
        source_code="print(1)",
        stdin_data="",
        time_limit_ms=250,
        memory_limit_kb=32,
    )

    assert request_body["run_timeout"] == 250
    assert request_body["memory_limit"] == 32 * 1024
    assert client_timeout == 8.25
    assert result.timed_out is True
    assert result.runtime_ms == 1200
    assert result.memory_kb == 2
    assert client_closed is True
