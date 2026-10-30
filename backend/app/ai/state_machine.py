"""
This module defines:
1. The interview stages (CLARIFICATION, APPROACH, LIVE_CODING, DRY_RUN, FOLLOW_UP, DEBRIEF)
2. The transition graphs
3. Validation guards
4. Structured output schema.
"""


from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

class InterviewStage(str, Enum):
    CLARIFICATION = "CLARIFICATION"
    APPROACH = "APPROACH"
    LIVE_CODING = "LIVE_CODING"
    DRY_RUN = "DRY_RUN"
    FOLLOW_UP = "FOLLOW_UP"
    DEBRIEF = "DEBRIEF"


# Deterministic stage progression map 

VALID_TRANSITIONS: Dict[InterviewStage, List[InterviewStage]] = {
    InterviewStage.CLARIFICATION: [InterviewStage.APPROACH, InterviewStage.DEBRIEF],
    InterviewStage.APPROACH: [InterviewStage.LIVE_CODING, InterviewStage.DEBRIEF],
    InterviewStage.LIVE_CODING: [InterviewStage.DRY_RUN, InterviewStage.DEBRIEF],
    InterviewStage.DRY_RUN: [InterviewStage.FOLLOW_UP, InterviewStage.DEBRIEF],
    InterviewStage.FOLLOW_UP: [InterviewStage.DEBRIEF],
    InterviewStage.DEBRIEF: []
}


# Validate the states which the agent is present in

class StageCriteria(BaseModel):
    """Gaurds before transitioning into subsequent stages"""

    model_config = ConfigDict(extra="forbid")

    # Clarification stage guards
    constraints_clarified: bool = False
    edge_cases_considered: bool = False

    # Approach stage guards
    approach_explained: bool = False
    time_complexity_stated: bool = False
    space_complexity_stated: bool = False
    approach_is_optimal_or_viable: bool = False

    # Coding stage guards
    code_syntactically_ready: bool = False

    # Dry run stage guards
    dry_run_completed: bool = False
    all_tests_passed: bool = False

class AgentTurnOutput(BaseModel):
    """Structured response schema returned by the LLM on every conversational turn."""

    spoken_response: str = Field(
        ...,
        description="The 1-3 sentence concise response spoken directly to the candidate."
    )

    detected_intent: str = Field(
        ...,
        description="Candidates's current action (e.g., asking_clarification, proposing_approach, coding, requesting_hint)."
    )

    suggested_stage_transition: Optional[InterviewStage] = Field(
        ...,
        description="Stage the AI proposes transitioning to, if the critieria are satisfied."
    )

    criteria_updates: Dict[str, bool] = Field(
        default_factory=dict,
        description="Stage criteria established by this turn; only include criteria supported by the conversation."
    )

    hint_tier_dispensed: Optional[int] = Field(
        None,
        ge=1,
        le=3,
        description="1(nudge), 2(structural clue), or 3 (direct instruction) if a hint was given."
    )

    detected_anti_pattern: Optional[str] = Field(
        None,
        description="Brief note on any incorrect logic, wrong Big-O, or unhandled edge cases."
    )


class InterviewStateMachine:
    def __init__(self, initial_stage: InterviewStage = InterviewStage.CLARIFICATION):
        self.current_stage = initial_stage
        self.criteria = StageCriteria()

    def can_transition_to(self, target_state: InterviewStage) -> bool:
        """Verifies topological validity and evaluates stage-specific deterministic transitions."""
        if target_state not in VALID_TRANSITIONS.get(self.current_stage, []):
            return False

        # Guard: CLARIFICATION -> APPROACH
        if self.current_stage == InterviewStage.CLARIFICATION and target_state == InterviewStage.APPROACH:
            return self.criteria.constraints_clarified or self.criteria.edge_cases_considered

        # Guard: APPROACH -> LIVE_CODING
        if self.current_stage == InterviewStage.APPROACH and target_state == InterviewStage.LIVE_CODING:
            return (
                self.criteria.approach_explained
                and self.criteria.time_complexity_stated
                and self.criteria.space_complexity_stated
                and self.criteria.approach_is_optimal_or_viable
            )

        # Guard: LIVE_CODING -> DRY_RUN
        if self.current_stage == InterviewStage.LIVE_CODING and target_state == InterviewStage.DRY_RUN:
            return self.criteria.code_syntactically_ready

        # Guard: DRY_RUN -> FOLLOW_UP
        if self.current_stage == InterviewStage.DRY_RUN and target_state == InterviewStage.FOLLOW_UP:
            return self.criteria.all_tests_passed or self.criteria.dry_run_completed

        # Transition ot DEBRIEF is always permitted (session conclusion)
        if target_state == InterviewStage.DEBRIEF:
            return True

        return False

    def transition(self, target_stage: InterviewStage) -> bool:
        """Executes the transition if guards pass."""
        if self.can_transition_to(target_stage):
            self.current_stage = target_stage
            return True
        return False

    def update_criteria(self, **kwargs) -> None:
        """Updates internal criteria flags based on candidate progress."""
        self.criteria = StageCriteria.model_validate(
            {**self.criteria.model_dump(), **kwargs}
        )