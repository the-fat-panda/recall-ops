"""Phase 3 graph wiring with durable CockroachDB checkpointing support."""

from __future__ import annotations

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph

from backend.orchestration.nodes import (
    build_escalation,
    run_memory_search,
    run_reason,
    run_recommend,
    run_triage,
    run_execute,
    run_writeback,
)
from backend.orchestration.state import AgentState

CHECKPOINT_MSGPACK_ALLOWLIST = (
    ("backend.schemas.alert", "Alert"),
    ("backend.schemas.candidate", "ScoredAction"),
    ("backend.schemas.candidate", "IncidentMatch"),
    ("backend.schemas.card", "ExperienceCard"),
)


def _after_reason(state: AgentState) -> str:
    return "recommend" if state.is_confident else "escalate"


def build_graph(checkpointer):
    checkpointer.serde = JsonPlusSerializer(
        allowed_msgpack_modules=CHECKPOINT_MSGPACK_ALLOWLIST
    )
    graph = StateGraph(AgentState)
    graph.add_node("triage", run_triage)
    graph.add_node("memory_search", run_memory_search)
    graph.add_node("reason", run_reason)
    graph.add_node("recommend", run_recommend)
    graph.add_node("execute", run_execute)
    graph.add_node("writeback", run_writeback)
    graph.add_node("escalate", build_escalation)
    graph.add_edge(START, "triage")
    graph.add_edge("triage", "memory_search")
    graph.add_edge("memory_search", "reason")
    graph.add_conditional_edges("reason", _after_reason)
    graph.add_edge("recommend", "execute")
    graph.add_edge("execute", "writeback")
    graph.add_edge("writeback", END)
    graph.add_edge("escalate", END)
    return graph.compile(checkpointer=checkpointer, interrupt_after=["recommend"])
