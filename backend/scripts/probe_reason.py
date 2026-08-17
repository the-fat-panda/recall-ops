# PROBE — throwaway. Proves memory_search + reason against seeded data. Run live.

from backend.orchestration.nodes import run_memory_search, run_reason
from backend.orchestration.state import AgentState
from backend.schemas.alert import Alert


def main() -> None:
    state = AgentState(
        alert=Alert(service="orders-api", symptom="pods restarting repeatedly", meta={}),
        run_id="probe-1",
        signature="CrashLoopBackOff",
    )
    run_memory_search(state)
    run_reason(state)
    print(f"match_count: {state.match_count}")
    for candidate in state.candidates:
        print(
            f"{candidate.action} / {candidate.success_count} / {candidate.fail_count} / "
            f"{candidate.confidence:.2f}"
        )
    print(f"chosen: {state.chosen.action if state.chosen else None}")
    print(f"is_confident: {state.is_confident}")


if __name__ == "__main__":
    main()
