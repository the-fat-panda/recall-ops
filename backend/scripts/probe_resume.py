# PROBE — throwaway. Proves LangGraph resume continues after an interrupt. Run live.

from __future__ import annotations

from uuid import uuid4

from langchain_cockroachdb import CockroachDBSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from pydantic import BaseModel, Field

from backend.infra.db import database_url


class ProbeState(BaseModel):
    value: int = 0
    steps: list[str] = Field(default_factory=list)


def node_a(state: ProbeState) -> ProbeState:
    return ProbeState(value=1, steps=[*state.steps, "a"])


def node_b(state: ProbeState) -> ProbeState:
    return ProbeState(value=2, steps=[*state.steps, "b"])


def node_c(state: ProbeState) -> ProbeState:
    return ProbeState(value=3, steps=[*state.steps, "c"])


def show_snapshot(label: str, snapshot) -> ProbeState:
    state = ProbeState.model_validate(snapshot.values)
    print(f"{label}_steps: {state.steps}")
    print(f"{label}_value: {state.value}")
    print(f"{label}_next: {snapshot.next}")
    return state


def main() -> None:
    builder = StateGraph(ProbeState)
    builder.add_node("node_a", node_a)
    builder.add_node("node_b", node_b)
    builder.add_node("node_c", node_c)
    builder.add_edge(START, "node_a")
    builder.add_edge("node_a", "node_b")
    builder.add_edge("node_b", "node_c")
    builder.add_edge("node_c", END)

    thread_id = f"recallops-resume-probe-{uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}
    print(f"thread_id: {thread_id}")
    with CockroachDBSaver.from_conn_string(database_url()) as checkpointer:
        checkpointer.setup()
        graph = builder.compile(checkpointer=checkpointer, interrupt_after=["node_b"])

        print("PHASE ONE — initial invoke")
        graph.invoke(ProbeState(), config)
        phase_one_snapshot = graph.get_state(config)
        phase_one_state = show_snapshot("phase_one", phase_one_snapshot)

        print("PHASE TWO — resume with None input")
        try:
            graph.invoke(None, config)
        except Exception as exc:
            print(f"None-input resume failed: {type(exc).__name__}: {exc}")
        phase_two_snapshot = graph.get_state(config)
        phase_two_state = show_snapshot("phase_two", phase_two_snapshot)

    phase_one_ok = phase_one_state.steps == ["a", "b"] and "node_c" in phase_one_snapshot.next
    phase_two_ok = (
        phase_two_state.steps == ["a", "b", "c"]
        and phase_two_state.value == 3
        and not phase_two_snapshot.next
    )
    if phase_one_ok and phase_two_ok:
        print("PASS: None-input resume continued at node_c without re-running node_b.")
    else:
        # A bad None-input result may have altered the first thread, so test Command on a
        # fresh interrupted thread instead of trying to resume the altered checkpoint.
        fallback_config = {"configurable": {"thread_id": f"recallops-resume-command-{uuid4()}"}}
        print("SECOND ATTEMPT — Command(resume={}) on a fresh interrupted thread")
        with CockroachDBSaver.from_conn_string(database_url()) as checkpointer:
            checkpointer.setup()
            fallback_graph = builder.compile(
                checkpointer=checkpointer,
                interrupt_after=["node_b"],
            )
            fallback_graph.invoke(ProbeState(), fallback_config)
            fallback_one_snapshot = fallback_graph.get_state(fallback_config)
            fallback_one_state = show_snapshot("command_phase_one", fallback_one_snapshot)
            fallback_graph.invoke(Command(resume={}), fallback_config)
            fallback_two_snapshot = fallback_graph.get_state(fallback_config)
            fallback_two_state = show_snapshot("command_phase_two", fallback_two_snapshot)
        fallback_ok = (
            fallback_one_state.steps == ["a", "b"]
            and "node_c" in fallback_one_snapshot.next
            and fallback_two_state.steps == ["a", "b", "c"]
            and fallback_two_state.value == 3
            and not fallback_two_snapshot.next
        )
        if fallback_ok:
            print("PASS: Command(resume={}) continued at node_c without re-running node_b.")
            return
        print("FAIL: neither resume mechanism matched the expected checkpoint continuation.")
        print(f"phase_one_snapshot: {phase_one_snapshot}")
        print(f"phase_two_snapshot: {phase_two_snapshot}")
        print(f"command_phase_one_snapshot: {fallback_one_snapshot}")
        print(f"command_phase_two_snapshot: {fallback_two_snapshot}")


if __name__ == "__main__":
    main()
