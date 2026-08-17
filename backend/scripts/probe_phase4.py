# PROBE — throwaway. Exercises Phase 4 approval, execution, and durable writeback. Run live.

from __future__ import annotations

import uuid

import httpx2
from langchain_cockroachdb import CockroachDBSaver

from backend.infra.db import database_url, query
from backend.orchestration.approval import approve_and_resume
from backend.orchestration.config import orders_api_url
from backend.orchestration.graph import build_graph
from backend.orchestration.state import AgentState
from backend.schemas.alert import Alert

SIGNATURE = "CrashLoopBackOff"
ACTION = "rollback deployment to prior revision"


def stats() -> dict:
    rows = query(
        "SELECT success_count, fail_count FROM fix_stats WHERE signature = %s AND action = %s",
        (SIGNATURE, ACTION),
    )
    return rows[0] if rows else {"success_count": 0, "fail_count": 0}


def sandbox(path: str) -> dict:
    with httpx2.Client(timeout=10.0) as client:
        response = client.post(f"{orders_api_url()}{path}") if path == "/reset" else client.get(f"{orders_api_url()}{path}")
        return {"status": response.status_code, "body": response.json()}


def main() -> None:
    run_id = f"phase4-live-{uuid.uuid4()}"
    thread_id = f"phase4-thread-{uuid.uuid4()}"
    unknown_run_id = f"phase4-unknown-{uuid.uuid4()}"
    unknown_thread_id = f"phase4-unknown-thread-{uuid.uuid4()}"
    incident_id = uuid.uuid5(uuid.NAMESPACE_URL, f"recallops-incident:{run_id}")
    attempt_id = uuid.uuid5(uuid.NAMESPACE_URL, f"recallops-attempt:{run_id}")
    checks: list[bool] = []

    print(f"run_id: {run_id}")
    print(f"incident_id: {incident_id}")
    print(f"attempt_id: {attempt_id}")
    print(f"reset: {sandbox('/reset')}")
    before = stats()

    with CockroachDBSaver.from_conn_string(database_url()) as checkpointer:
        checkpointer.setup()
        graph = build_graph(checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        graph.invoke(
            AgentState(
                alert=Alert(
                    service="orders-api",
                    symptom="pods restarting repeatedly, back-off restarting failed container",
                    meta={},
                ),
                run_id=run_id,
            ),
            config,
        )
        paused = graph.get_state(config)
        paused_state = AgentState.model_validate(paused.values)
        broken_health = sandbox("/health")
        print(f"case_a_paused_next: {paused.next}")
        print(f"case_a_signature: {paused_state.signature}")
        print(f"case_a_chosen: {paused_state.chosen.action if paused_state.chosen else None}")
        print(f"case_a_health: {broken_health}")
        checks.append(paused.next == ("execute",))
        checks.append(paused_state.signature == SIGNATURE and paused_state.chosen is not None and paused_state.chosen.action == ACTION)
        checks.append(broken_health["body"].get("version") == "v2.8.1")

        approve_and_resume(graph, config)
        completed = graph.get_state(config)
        completed_state = AgentState.model_validate(completed.values)
        after = stats()
        rows = query(
            "SELECT i.id AS incident_id, a.id AS attempt_id, a.result FROM incidents i JOIN attempts a ON a.incident_id = i.id WHERE i.id = %s AND a.id = %s",
            (str(incident_id), str(attempt_id)),
        )
        print(f"case_a_completed_next: {completed.next}")
        print(f"case_a_execution: {completed_state.execution_result}")
        print(f"case_a_writeback_done: {completed_state.writeback_done}")
        print(f"case_a_fix_stats_before: {before}")
        print(f"case_a_fix_stats_after: {after}")
        print(f"case_a_live_rows: {rows}")
        checks.append(completed_state.execution_result is not None and completed_state.execution_result.get("status") == "executed" and completed_state.execution_result.get("result") == "success")
        checks.append(completed_state.writeback_done and after["success_count"] == before["success_count"] + 1)
        checks.append(len(rows) == 1 and rows[0]["result"] == "success")

        before_replay = stats()
        print(f"reset_before_case_b: {sandbox('/reset')}")
        replay_thread = f"phase4-replay-{uuid.uuid4()}"
        replay_config = {"configurable": {"thread_id": replay_thread}}
        graph.invoke(
            AgentState(
                alert=Alert(
                    service="orders-api",
                    symptom="pods restarting repeatedly, back-off restarting failed container",
                    meta={},
                ),
                run_id=run_id,
            ),
            replay_config,
        )
        replay_paused = graph.get_state(replay_config)
        print(f"case_b_paused_next: {replay_paused.next}")
        approve_and_resume(graph, replay_config)
        replayed = AgentState.model_validate(graph.get_state(replay_config).values)
        after_replay = stats()
        attempt_rows = query("SELECT id FROM attempts WHERE id = %s", (str(attempt_id),))
        print(f"case_b_execution: {replayed.execution_result}")
        print(f"case_b_fix_stats_before: {before_replay}")
        print(f"case_b_fix_stats_after: {after_replay}")
        print(f"case_b_attempt_row_count: {len(attempt_rows)}")
        checks.append(replay_paused.next == ("execute",))
        checks.append(
            before_replay == after_replay
            and len(attempt_rows) == 1
            and replayed.writeback_done
        )

        print(f"reset_before_case_c: {sandbox('/reset')}")
        unknown_config = {"configurable": {"thread_id": unknown_thread_id}}
        graph.invoke(
            AgentState(
                alert=Alert(service="orders-api", symptom="quantum flux capacitor desync in the reactor", meta={}),
                run_id=unknown_run_id,
            ),
            unknown_config,
        )
        unknown = graph.get_state(unknown_config)
        unknown_state = AgentState.model_validate(unknown.values)
        unknown_incident_id = uuid.uuid5(uuid.NAMESPACE_URL, f"recallops-incident:{unknown_run_id}")
        unknown_rows = query("SELECT id FROM incidents WHERE id = %s", (str(unknown_incident_id),))
        untouched_health = sandbox("/health")
        print(f"case_c_outcome: {unknown_state.outcome}")
        print(f"case_c_execution: {unknown_state.execution_result}")
        print(f"case_c_live_rows: {unknown_rows}")
        print(f"case_c_health: {untouched_health}")
        checks.append(unknown_state.outcome == "ESCALATED" and not unknown_rows)
        checks.append(untouched_health["body"].get("version") == "v2.8.1")

    print(f"final_reset: {sandbox('/reset')}")
    print("PASS" if all(checks) else "FAIL")


if __name__ == "__main__":
    main()
