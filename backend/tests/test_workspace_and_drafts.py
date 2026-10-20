import uuid

import pytest
from sqlalchemy import func, select

from app.models.entities import UserDraft, UserProblemStatus


async def create_user(client, username: str | None = None) -> uuid.UUID:
    response = await client.post(
        "/api/v1/users/demo",
        params={"username": username or f"user-{uuid.uuid4().hex[:8]}"},
    )
    assert response.status_code == 200
    return uuid.UUID(response.json()["user_id"])


async def create_problem(client, slug: str = "two-sum") -> dict:
    response = await client.post(
        "/api/v1/problems",
        json={
            "slug": slug,
            "title": "Two Sum",
            "difficulty": "EASY",
            "prob_description": "Return the indices of two numbers that sum to target.",
            "prob_examples": [{"input": "[2,7], 9", "output": "[0,1]"}],
            "prob_constraints": "2 <= numbers.length",
            "time_limit_ms": 1000,
            "memory_limit_kb": 65536,
            "language_templates": [
                {
                    "template_language": "python",
                    "boilerplate": "class Solution:\n    def twoSum(self, nums, target):\n        pass",
                    "driver_harness": "# DRIVER_SECRET: hidden grader implementation",
                }
            ],
            "test_cases": [
                {
                    "expected_input": "[2,7,11,15]\n9",
                    "expected_output": "[0, 1]",
                    "is_sample": True,
                    "ordinal_order": 1,
                },
                {
                    "expected_input": "[3,2,4]\n6",
                    "expected_output": "[1, 2]",
                    "is_sample": True,
                    "ordinal_order": 2,
                },
                {
                    "expected_input": "[3,3]\n6",
                    "expected_output": "[0, 1]",
                    "is_sample": False,
                    "ordinal_order": 3,
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_create_problem_returns_created(client):
    response = await client.post(
        "/api/v1/problems",
        json={
            "slug": "created-problem",
            "title": "Created Problem",
            "difficulty": "EASY",
            "prob_description": "Description",
            "prob_constraints": "None",
            "language_templates": [
                {
                    "template_language": "python",
                    "boilerplate": "def solve(): pass",
                    "driver_harness": "print('hidden')",
                }
            ],
            "test_cases": [
                {
                    "expected_input": "1",
                    "expected_output": "1",
                    "is_sample": True,
                },
                {
                    "expected_input": "2",
                    "expected_output": "2",
                    "is_sample": False,
                },
            ],
        },
    )
    assert response.status_code == 201
    assert response.json()["slug"] == "created-problem"


@pytest.mark.asyncio
async def test_workspace_exposes_only_public_templates_and_sample_cases(client):
    await create_problem(client)

    response = await client.get("/api/v1/problems/two-sum")

    assert response.status_code == 200
    workspace = response.json()
    assert len(workspace["sample_test_cases"]) == 2
    assert {case["expected_input"] for case in workspace["sample_test_cases"]} == {
        "[2,7,11,15]\n9",
        "[3,2,4]\n6",
    }
    assert "DRIVER_SECRET" not in response.text
    assert len(workspace["language_templates"]) == 1
    assert workspace["language_templates"][0]["boilerplate"].startswith("class Solution")
    assert "driver_harness" not in workspace["language_templates"][0]
    assert workspace["saved_drafts"] == {}


@pytest.mark.asyncio
async def test_draft_autosave_upserts_one_row_and_survives_cache_failure(
    client, db_session, redis_client
):
    await create_problem(client)
    user_id = await create_user(client)

    first = await client.put(
        "/api/v1/problems/two-sum/draft",
        json={"user_id": str(user_id), "language": "python", "code": "first version"},
    )
    second = await client.put(
        "/api/v1/problems/two-sum/draft",
        json={"user_id": str(user_id), "language": "python", "code": "updated version"},
    )

    assert first.status_code == second.status_code == 200
    assert await db_session.scalar(select(func.count()).select_from(UserDraft)) == 1
    saved = await db_session.scalar(select(UserDraft))
    assert saved.code == "updated version"
    workspace = (
        await client.get("/api/v1/problems/two-sum", params={"user_id": str(user_id)})
    ).json()
    key = f"draft:{user_id}:{workspace['problem_id']}:python"
    assert redis_client.expirations[key] == 86400

    redis_client.fail_set = True
    fallback_write = await client.put(
        "/api/v1/problems/two-sum/draft",
        json={"user_id": str(user_id), "language": "python", "code": "database only"},
    )
    assert fallback_write.status_code == 200
    assert await db_session.scalar(select(func.count()).select_from(UserDraft)) == 1
    assert await db_session.scalar(select(UserDraft.code)) == "database only"


@pytest.mark.asyncio
async def test_workspace_loads_user_draft_but_not_another_users_draft(
    client, redis_client
):
    await create_problem(client)
    user_a = await create_user(client)
    user_b = await create_user(client)
    saved_code = "class Solution:\n    def twoSum(self, nums, target): return [0, 1]"
    saved = await client.put(
        "/api/v1/problems/two-sum/draft",
        json={"user_id": str(user_a), "language": "python", "code": saved_code},
    )
    assert saved.status_code == 200

    user_a_workspace = await client.get(
        "/api/v1/problems/two-sum", params={"user_id": str(user_a)}
    )
    user_b_workspace = await client.get(
        "/api/v1/problems/two-sum", params={"user_id": str(user_b)}
    )

    assert user_a_workspace.json()["saved_drafts"] == {"python": saved_code}
    assert user_b_workspace.json()["saved_drafts"] == {}


@pytest.mark.asyncio
async def test_redis_draft_takes_precedence_and_unavailable_redis_falls_back(
    client, redis_client
):
    await create_problem(client)
    user_id = await create_user(client)
    await client.put(
        "/api/v1/problems/two-sum/draft",
        json={"user_id": str(user_id), "language": "python", "code": "postgres draft"},
    )
    workspace = (
        await client.get("/api/v1/problems/two-sum", params={"user_id": str(user_id)})
    ).json()
    redis_key = f"draft:{user_id}:{workspace['problem_id']}:python"
    redis_client.values[redis_key] = "redis draft"

    cached_workspace = await client.get(
        "/api/v1/problems/two-sum", params={"user_id": str(user_id)}
    )
    assert cached_workspace.json()["saved_drafts"]["python"] == "redis draft"

    redis_client.fail_get = True
    fallback_workspace = await client.get(
        "/api/v1/problems/two-sum", params={"user_id": str(user_id)}
    )
    assert fallback_workspace.status_code == 200
    assert fallback_workspace.json()["saved_drafts"]["python"] == "postgres draft"


@pytest.mark.asyncio
async def test_bookmark_fields_are_idempotent_and_independently_updatable(
    client, db_session
):
    problem = await create_problem(client)
    user_id = await create_user(client)
    endpoint = f"/api/v1/problems/{problem['slug']}/bookmark"
    payload = {
        "user_id": str(user_id),
        "is_favourite": True,
        "solve_again": True,
    }

    first = await client.patch(endpoint, json=payload)
    second = await client.patch(endpoint, json=payload)
    preserve_favourite = await client.patch(
        endpoint, json={"user_id": str(user_id), "solve_again": False}
    )

    assert first.status_code == second.status_code == 200
    assert second.json()["is_favourite"] is True
    assert second.json()["solve_again"] is True
    assert preserve_favourite.json()["is_favourite"] is True
    assert preserve_favourite.json()["solve_again"] is False
    row = await db_session.scalar(select(UserProblemStatus))
    assert row.is_favourite is True
    assert row.solve_again is False
    anonymous_catalog = await client.get("/api/v1/problems")
    assert anonymous_catalog.json()[0]["status"] is None
    assert anonymous_catalog.json()[0]["is_favourite"] is False
    assert anonymous_catalog.json()[0]["solve_again"] is False
    catalog = await client.get("/api/v1/problems", params={"user_id": str(user_id)})
    assert catalog.json()[0]["status"] is None
    assert catalog.json()[0]["is_favourite"] is True
    assert catalog.json()[0]["solve_again"] is False


@pytest.mark.asyncio
async def test_draft_rejects_unknown_user(client):
    await create_problem(client)
    response = await client.put(
        "/api/v1/problems/two-sum/draft",
        json={
            "user_id": str(uuid.uuid4()),
            "language": "python",
            "code": "draft",
        },
    )
    assert response.status_code == 404
