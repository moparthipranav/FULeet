from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import redis.asyncio as aioredis
from sqlalchemy import select


from app.models.entities import Problem
from app.ai.context_builder import ContextEngine
from app.ai.prompts.system_persona import build_system_prompt
from app.ai.state_machine import InterviewStateMachine, AgentTurnOutput, InterviewStage
from app.ai.llm_client import LLMClient

class InterviewAgent:

    def __init__(self, db: AsyncSession, redis: aioredis.Redis):
        self.db = db
        self.redis = redis
        self.context_engine = ContextEngine(db, redis)
        self.llm_client = LLMClient()


    async def step(
        self,
        problem_slug: str,
        user_id:str,
        sm: InterviewStateMachine,
        candidate_utterance: str,
        chat_history: list[dict[str, str]],
        language: str = "python",
        sandbox_result: Optional[Dict[str, Any]] = None,
        total_hints: int = 0,
    ) -> AgentTurnOutput:

        # Fetching the problem entity
        stmt = (
            select(Problem)
            .where(Problem.slug == problem_slug)
            .options(selectinload(Problem.test_cases)) # Eagerly loads related objects or collection by emitting a second separate SELECT query with a primary key IN (...) CLAUSE
        )

        problem = await self.db.scalar(stmt)
        if not problem:
            raise ValueError(f"Problem '{problem_slug}' not found.")

        # Compile bounded context via ContextEngine
        compiled = await self.context_engine.compile_context(
            problem=problem,
            user_id=user_id,
            current_stage=sm.current_stage,
            chat_history=chat_history,
            language=language,
            sandbox_result=sandbox_result,
        )

        # Building the socratic prompt
        base_prompt = build_system_prompt(
            problem_title = problem.title,
            problem_description=problem.prob_description,
            problem_constraints=problem.prob_constraints,
            current_stage=sm.current_stage,
            hint_tier_count=total_hints,
        )

        system_prompt = f"{base_prompt}\n\n{compiled.system_prompt_additions}"

        # Prepare the message queue
        messages = list(compiled.injected_messages)
        messages.append({"role": "user", "content": candidate_utterance})

        turn_output = await self.llm_client.generate_turn(system_prompt, messages)
        sm.update_criteria(**turn_output.criteria_updates)

        if turn_output.suggested_stage_transition:
            target = turn_output.suggested_stage_transition
            if sm.can_transition_to(target):
                sm.transition(target)
            else:
                turn_output.suggested_stage_transition = None

        return turn_output
        