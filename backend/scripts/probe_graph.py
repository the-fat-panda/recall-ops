# PROBE — throwaway. Runs the full Phase 3 graph to the interrupt. Run live.

from backend.infra.db import database_url
from backend.orchestration.graph import build_graph
from backend.orchestration.state import AgentState
from backend.schemas.alert import Alert
from langchain_cockroachdb import CockroachDBSaver


def print_state(values: dict) -> None:
    state = AgentState.model_validate(values)
    print(f"signature: {state.signature}")
    print(f"match_count: {state.match_count}")
    print(f"chosen: {state.chosen.action if state.chosen else None}")
    print(f"confidence_band: {state.confidence_band}")
    print(f"outcome: {state.outcome}")
    print(f"experience_card: {state.experience_card is not None}")
    print(f"explanation_len: {len(state.explanation)}")
    print(f"explanation_head: {state.explanation[:120]}")
    print(f"explanation_tail: {state.explanation[-60:]}")


def main() -> None:
    with CockroachDBSaver.from_conn_string(database_url()) as checkpointer:
        checkpointer.setup()
        graph = build_graph(checkpointer)
        config = {"configurable": {"thread_id": "probe-graph-1"}}
        graph.invoke(
            AgentState(
                alert=Alert(
                    service="orders-api",
                    symptom="pods restarting repeatedly, back-off restarting failed container",
                    meta={},
                ),
                run_id="probe-g1",
            ),
            config,
        )
        print_state(graph.get_state(config).values)

        # Escalation check: an unseen alert may classify to a signature with no fix_stats.
        unseen_config = {"configurable": {"thread_id": "probe-graph-2"}}
        graph.invoke(
            AgentState(
                alert=Alert(
                    service="orders-api",
                    symptom="quantum flux capacitor desync in the reactor",
                    meta={},
                ),
                run_id="probe-g2",
            ),
            unseen_config,
        )
        print_state(graph.get_state(unseen_config).values)


if __name__ == "__main__":
    main()
