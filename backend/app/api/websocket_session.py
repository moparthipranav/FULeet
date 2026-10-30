import json
from typing import Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.database import get_db
from app.core.redis import get_redis
from app.ai.agent import InterviewAgent
from app.ai.session_manager import InterviewSessionManager


router = APIRouter(prefix="/ws", tags=["interview Session"])


class InterviewTurnRequest(BaseModel):
    utterance: str
    language: str = "python"
    sandbox_result: dict[str, Any] | None = None


@router.websocket("/interview/{problem_slug}/{user_id}")
async def interview_websocket(
    websocket: WebSocket,
    problem_slug: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis),
):
    await websocket.accept()
    session_mgr = InterviewSessionManager(redis_client, user_id, problem_slug)
    sm = await session_mgr.load_state_machine()
    agent = InterviewAgent(db, redis_client)

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                data = InterviewTurnRequest.model_validate_json(raw_text)
            except (json.JSONDecodeError, ValidationError):
                await websocket.send_json({"error": "Invalid interview turn payload"})
                continue

            utterance = data.utterance
            language = data.language
            sandbox_result = data.sandbox_result

            chat_history = await session_mgr.get_history()
            total_hints = await session_mgr.get_hint_count()

            # Execute turn
            turn_output = await agent.step(
                problem_slug=problem_slug,
                user_id=user_id,
                sm=sm,
                candidate_utterance=utterance,
                chat_history=chat_history,
                language=language,
                sandbox_result=sandbox_result,
                total_hints=total_hints,
            )

            # Record hint count if dispensed
            if turn_output.hint_tier_dispensed:
                await session_mgr.record_hint_used(turn_output.hint_tier_dispensed)

            # Persist transcript
            await session_mgr.append_message("user", utterance)
            await session_mgr.append_message("assistant", turn_output.spoken_response)
            await session_mgr.save_state_machine(sm)

            await websocket.send_text(
                json.dumps(
                    {
                        "spoken_response": turn_output.spoken_response,
                        "current_stage": sm.current_stage.value,
                        "transitioned": turn_output.suggested_stage_transition is not None,
                        "hint_tier": turn_output.hint_tier_dispensed,
                        "anti_pattern": turn_output.detected_anti_pattern,
                    }
                )
            )
            
    except WebSocketDisconnect:
        pass
    