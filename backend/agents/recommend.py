"""LLM explanation over a deterministic recommendation choice."""

from __future__ import annotations

import json
from pathlib import Path

from backend.agents.llm_client import LLMClient
from backend.orchestration.state import AgentState
from backend.schemas.card import ExperienceCard

RECOMMEND_PROMPT_PATH = Path(__file__).with_name("prompts") / "recommend_system.md"


def run_recommend(state: AgentState) -> AgentState:
    if state.chosen is None:
        raise RuntimeError("Recommendation requires a chosen action.")
    failed_history = [
        f"{candidate.action}: {candidate.fail_count} failed attempt(s)"
        for candidate in state.candidates
        if candidate.fail_count > 0
    ]
    explanation_input = {
        "chosen_action": state.chosen.action,
        "candidates": [candidate.model_dump(mode="json") for candidate in state.candidates],
    }
    state.explanation = LLMClient().complete(
        RECOMMEND_PROMPT_PATH.read_text(encoding="utf-8"),
        json.dumps(explanation_input),
    )
    state.outcome = "RECOMMENDED"
    state.experience_card = ExperienceCard(
        signature=state.signature,
        match_summary=f"Found {state.match_count} similar past incident(s).",
        live_evidence=state.live_evidence,
        candidates=state.candidates,
        chosen_action=state.chosen.action,
        failed_history=failed_history,
        confidence_band=state.confidence_band,
        explanation=state.explanation,
        outcome="RECOMMENDED",
    )
    return state
