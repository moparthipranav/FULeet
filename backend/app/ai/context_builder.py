"""
Building the context for the AI model -> context engineering. 
Core components of an AI context stack
1. System Instructions: Clear foundational rules, role definitions and behavioural guidelines
2. User Input: The immediate prompt or task at hand
3. Retrieved facts (RAG): Dynamic or static documents, PDFs or database lookups pulled just-in-time
4. Tools/MCPs: Executable functions the AI can invoke
5. Short-term notes: active working memory or recent conversational history
6. Long-term memory: Persistent external storage or knowledge graphs for past decisions.
7. Output format (schames): Constraints, templates or JSON structures that lock the shape of the response.


Core Architecture

There are Incoming streams of context which the AI model can use, which are 1) Problem Truth 2) Saved Code & Draft 3) Candidate utterance and 4) Piston Telemetry data

The whole architecture is divided into 4 subsystems:
Subsystem A: Stage-Aware masking matrix. This masks the information which is not necessary to include in the context when the agent is in a specific state (LIVE_CODE, CLARIFICATION etc)
Subsystem B: AST extraction and semantic diffing. This makes it possible to not send the whole code written by the user everytime to the AI agent which can reduce the token costs
Subsystem C: Telemetry data minimalizer. Piston telemetry can give a lot of information. This information should be effectively summarized to avoid huge token sizes
Subsystem D: Transcript sliding window & hierarchial summarizer
Subsystem E: Hard Token Budget Allocation.
"""
import ast
import logging
import uuid
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional, List
import json
from dataclasses import dataclass

from app.models.entities import Problem, UserDraft
from app.ai.state_machine import InterviewStage

logger = logging.getLogger(__name__)


@dataclass
class CompiledContext:
    system_prompt_additions: str
    injected_messages: List[Dict[str, str]]
    metadata: Dict[str, Any]

class ContextEngine:
    def __init__(self, db: AsyncSession, redis: aioredis.Redis):
        self.db = db
        self.redis = redis

    def _analyze_code(self, code: str, language: str) -> Dict[str, Any]:
        """Performs static code analysis and AST inspection without executing the code."""
        if not code.strip():
            return {"empty": True, "syntax_valid": True}
        if language.lower() not in {"python", "py"}:
            return {"empty": False, "syntax_valid": None}

        try:
            tree = ast.parse(code)
            functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
            has_loops = any(isinstance(n, (ast.For, ast.While)) for n in ast.walk(tree))
            return {
                "empty": False,
                "syntax_valid": True,
                "functions_defined": functions,
                "contains_loops": has_loops,
            }
        except SyntaxError as e:
            return {
                "empty": False,
                "syntax_valid": False,
                "syntax_error": f"Line {e.lineno}: {e.msg}",
            }

    def _truncate_telemetry(self, raw_telemetry: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Sanitizes and bounds sandbox test results to prevent context explosions"""
        if not raw_telemetry:
            return None

        clean = {}
        for key in ["input", "expected", "actual", "error"]:
            val = str(raw_telemetry.get(key, ""))
            if len(val) > 200:
                val = val[:200] + "... [truncated]"
            clean[key] = val
        return clean

    async def get_episodic_summary(self, user_id: str, slug: str) -> Dict[str, Any]:
        """Fetches the compact running summary of decisions from Redis."""
        key = f"interview_summary:{user_id}:{slug}"
        data = await self.redis.get(key)
        if data:
            return json.loads(data)
        
        return {
            "clarified_points": [],
            "agreed_complexity": None,
            "hints_dispensed": 0
        }

    async def compile_context(
        self,
        problem: Problem,
        user_id: str,
        current_stage: InterviewStage,
        chat_history: List[Dict[str, str]],
        language: str = "python",
        sandbox_result: Optional[Dict[str, Any]] = None,
    ) -> CompiledContext:

        # Fetch the current draft
        draft_key = f"draft:{user_id}:{problem.problem_id}:{language}"
        try:
            current_code = await self.redis.get(draft_key)
        except aioredis.RedisError:
            logger.warning("Redis draft lookup failed; using PostgreSQL draft")
            current_code = None

        if current_code is None:
            current_code = await self.db.scalar(
                select(UserDraft.code).where(
                    UserDraft.user_id == uuid.UUID(user_id),
                    UserDraft.problem_id == problem.problem_id,
                    UserDraft.language == language,
                )
            )
        current_code = current_code or ""
        if isinstance(current_code, bytes):
            current_code = current_code.decode("utf-8", errors="replace")
        code_meta = self._analyze_code(current_code, language)

        # Fetch the episodic summary
        summary = await self.get_episodic_summary(user_id, problem.slug)

        # Clean telemetry
        telemetry = self._truncate_telemetry(sandbox_result)

        # Apply stage masking matrix
        prompt_sections = [
            f"=== INTERVIEW EPISODIC STATE ===",
            f"Agreed Complexity: {summary.get('agreed_complexity', 'Not yet formalized')}",
            f"Clarified Points: {', '.join(summary.get('clarified_points', [])) or 'None'}",
            f"Hints Used Count: {summary.get('hints_dispensed', 0)}",
        ]

        if current_stage in [InterviewStage.LIVE_CODING, InterviewStage.DRY_RUN]:
            prompt_sections.append(f"\n--- Candidate Code Buffer ({language}) ---")
            if code_meta["syntax_valid"] is False:
                prompt_sections.append(f"[SYNTAX WARNING: {code_meta['syntax_error']}]")
            prompt_sections.append(f"```{language}\n{current_code}\n```")
        
        if current_stage == InterviewStage.DRY_RUN and telemetry:
            prompt_sections.append(f"\n=== TEST EXECUTION TELEMETRY ===")
            prompt_sections.append(json.dumps(telemetry, indent=2))

        recent_turns = chat_history[-6:] if len(chat_history) > 6 else chat_history

        return CompiledContext(
            system_prompt_additions="\n".join(prompt_sections),
            injected_messages=recent_turns,
            metadata={
                "code_empty": code_meta["empty"],
                "syntax_valid": code_meta.get("syntax_valid", True),
                "token_budget_target": 2048,
            }
        )
        


        
