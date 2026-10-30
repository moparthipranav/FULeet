import json

import pytest
from sqlalchemy import select

from app.ai.context_builder import ContextEngine
from app.ai.llm_client import LLMClient
from app.ai.prompts.system_persona import build_system_prompt
from app.ai.session_manager import InterviewSessionManager
from app.ai.state_machine import InterviewStage, InterviewStateMachine
from app.models.entities import Problem

from tests.test_workspace_and_drafts import create_problem, create_user


@pytest.mark.asyncio
async def test_context_engine_reads_persisted_draft_when_cache_misses(
    client, db_session, redis_client
):
    problem_ref = await create_problem(client)
    user_id = await create_user(client)
    code = "class Solution:\n    def twoSum(self, nums, target): return [0, 1]"
    await client.put(
        f"/api/v1/problems/{problem_ref['slug']}/draft",
        json={"user_id": str(user_id), "language": "python", "code": code},
    )
    workspace = (
        await client.get(
            f"/api/v1/problems/{problem_ref['slug']}",
            params={"user_id": str(user_id)},
        )
    ).json()
    cache_key = f"draft:{user_id}:{workspace['problem_id']}:python"
    problem = await db_session.scalar(
        select(Problem).where(Problem.slug == problem_ref["slug"])
    )
    context = await ContextEngine(db_session, redis_client).compile_context(
        problem=problem,
        user_id=str(user_id),
        current_stage=InterviewStage.LIVE_CODING,
        chat_history=[],
    )
    redis_client.values.pop(cache_key)

    restored = await ContextEngine(db_session, redis_client).compile_context(
        problem=problem,
        user_id=str(user_id),
        current_stage=InterviewStage.LIVE_CODING,
        chat_history=[],
    )
    assert code in context.system_prompt_additions
    assert code in restored.system_prompt_additions
    assert restored.metadata["code_empty"] is False


@pytest.mark.asyncio
async def test_interview_history_key_and_hint_count_are_consistent(redis_client):
    manager = InterviewSessionManager(redis_client, "user", "two-sum")

    await manager.record_hint_used(2)

    assert manager.history_key == "session:user:two-sum:history"
    assert await manager.get_hint_count() == 1


def test_state_machine_accepts_updated_criteria_and_correct_debrief_value():
    machine = InterviewStateMachine()
    machine.update_criteria(constraints_clarified=True)

    assert machine.transition(InterviewStage.APPROACH)
    assert InterviewStage.DEBRIEF.value == "DEBRIEF"
    assert machine.transition(InterviewStage.DEBRIEF)

    with pytest.raises(ValueError):
        machine.update_criteria(unknown_criteria=True)


def test_interview_prompt_contains_valid_json_schema_example():
    prompt = build_system_prompt(
        problem_title="Example",
        problem_description="Description",
        problem_constraints="None",
        current_stage=InterviewStage.CLARIFICATION,
    )
    schema = prompt.split("schema:\n", maxsplit=1)[1].split(
        "\n\nUse 1, 2, or 3", maxsplit=1
    )[0]

    assert json.loads(schema)["criteria_updates"] == {
        "constraints_clarified": True
    }


@pytest.mark.asyncio
async def test_session_manager_reads_legacy_debrief_state(redis_client):
    manager = InterviewSessionManager(redis_client, "user", "two-sum")
    redis_client.values[manager.state_key] = json.dumps(
        {"current_stage": "DEBREIF", "criteria": {}}
    )

    assert (await manager.load_state_machine()).current_stage is InterviewStage.DEBRIEF


@pytest.mark.asyncio
async def test_session_manager_migrates_legacy_history_key(redis_client):
    manager = InterviewSessionManager(redis_client, "user", "two-sum")
    redis_client.values[manager.legacy_history_key] = json.dumps(
        [{"role": "assistant", "content": "Welcome"}]
    )

    assert await manager.get_history() == [
        {"role": "assistant", "content": "Welcome"}
    ]
    assert redis_client.values[manager.history_key] == redis_client.values[
        manager.legacy_history_key
    ]


@pytest.mark.asyncio
async def test_llm_client_reads_openai_message_content(monkeypatch):
    class MockResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "spoken_response": "Consider the edge case.",
                                    "detected_intent": "clarifying",
                                    "suggested_stage_transition": None,
                                }
                            )
                        }
                    }
                ]
            }

    class MockAsyncClient:
        def __init__(self, timeout):
            assert timeout == 30.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, _url, json, headers):
            assert headers["Authorization"] == "Bearer test-key"
            return MockResponse()

    monkeypatch.setattr("app.ai.llm_client.httpx.AsyncClient", MockAsyncClient)
    response = await LLMClient(api_key="test-key").generate_turn("system", [])

    assert response.spoken_response == "Consider the edge case."


def test_websocket_route_is_declared():
    from app.api.websocket_session import router

    assert any(
        getattr(route, "path", None)
        == "/ws/interview/{problem_slug}/{user_id}"
        for route in router.routes
    )
