"""
The goal of this module is to build a session manager to handle session persistence, transcript appending and criteria tracking in Redis.
"""
import json
import redis.asyncio as aioredis
from app.ai.state_machine import InterviewStage, InterviewStateMachine
from typing import List, Dict 


class InterviewSessionManager:

    def __init__(self, redis: aioredis.Redis, user_id: str, problem_slug: str):
        self.redis = redis
        self.user_id = user_id
        self.problem_slug = problem_slug

        # Redis namespace keys
        self.state_key = f"session:{user_id}:{problem_slug}:state"
        self.history_key = f"session:{user_id}:{problem_slug}:history"
        self.legacy_history_key = f"session:{user_id}: {problem_slug}: history"
        self.summary_key = f"interview_summary:{user_id}:{problem_slug}"

    async def load_state_machine(self) -> InterviewStateMachine:
        raw_state = await self.redis.get(self.state_key)
        if raw_state:
            data = json.loads(raw_state)
            stage = data["current_stage"]
            if stage == "DEBREIF":
                stage = InterviewStage.DEBRIEF.value
            sm = InterviewStateMachine(initial_stage=InterviewStage(stage))
            criteria = data.get("criteria", {})
            if "edge_cases_clonsidered" in criteria:
                criteria["edge_cases_considered"] = criteria.pop(
                    "edge_cases_clonsidered"
                )
            sm.criteria = sm.criteria.model_validate(criteria)
            return sm
        return InterviewStateMachine(initial_stage=InterviewStage.CLARIFICATION)

    async def save_state_machine(self, sm:InterviewStateMachine) -> None:
        payload = {
            "current_stage": sm.current_stage.value,
            "criteria": sm.criteria.model_dump()
        }
        await self.redis.set(self.state_key, json.dumps(payload), ex=86400)

    async def get_history(self) -> List[Dict[str, str]]:
        raw = await self.redis.get(self.history_key)
        if raw is None:
            raw = await self.redis.get(self.legacy_history_key)
            if raw is not None:
                await self.redis.set(self.history_key, raw, ex=86400)
        return json.loads(raw) if raw else []

    async def append_message(self, role: str, content: str) -> None:
        history = await self.get_history()
        history.append({"role": role, "content": content})
        await self.redis.set(self.history_key, json.dumps(history), ex=86400)

    async def record_hint_used(self, tier: int) -> int:
        raw = await self.redis.get(self.summary_key)
        summary = json.loads(raw) if raw else {"clarified_points": [], "agreed_complexity": None, "hints_dispensed": 0}
        summary["hints_dispensed"] = summary.get("hints_dispensed", 0) + 1
        await self.redis.set(self.summary_key, json.dumps(summary), ex=86400)
        return summary["hints_dispensed"]

    async def get_hint_count(self) -> int:
        raw = await self.redis.get(self.summary_key)
        if not raw:
            return 0
        summary = json.loads(raw)
        return int(summary.get("hints_dispensed", 0))
