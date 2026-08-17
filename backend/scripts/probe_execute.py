# PROBE — throwaway. Tests the Phase 4 execute node and approval gate. Run live.

from __future__ import annotations

import httpx2

from backend.orchestration.config import orders_api_url
from backend.orchestration.nodes import run_execute
from backend.orchestration.state import AgentState
from backend.schemas.alert import Alert
from backend.schemas.candidate import ScoredAction


def make_state(action: str, approved: bool) -> AgentState:
    return AgentState(
        alert=Alert(service="orders-api", symptom="pool exhausted", meta={}),
        run_id="probe-execute",
        signature="DBConnectionPoolExhaustion",
        chosen=ScoredAction(
            action=action,
            success_count=1,
            fail_count=0,
            confidence=1.0,
            freshness=1.0,
        ),
        approved=approved,
    )


def health(client: httpx2.Client, base_url: str) -> dict:
    response = client.get(f"{base_url}/health", timeout=5.0)
    return {"http_status": response.status_code, "body": response.json()}


def main() -> None:
    base_url = orders_api_url()
    passed = []
    with httpx2.Client(timeout=10.0) as client:
        try:
            print("CASE 1 — approved mapped rollback")
            client.post(f"{base_url}/reset")
            case_one = run_execute(make_state("rollback deployment to prior revision", True))
            print(case_one.execution_result)
            case_one_health = case_one.execution_result["health_response"]["body"]
            passed.append(
                case_one.execution_result["status"] == "executed"
                and case_one.execution_result["result"] == "success"
                and case_one_health.get("version") == "v2.8.0"
                and case_one_health.get("pool_size") == 20
            )

            print("CASE 2 — not approved")
            client.post(f"{base_url}/reset")
            case_two = run_execute(make_state("rollback deployment to prior revision", False))
            case_two_health = health(client, base_url)
            print(case_two.execution_result)
            print(f"health_after_gate: {case_two_health}")
            passed.append(
                case_two.execution_result["status"] == "not_approved"
                and "result" not in case_two.execution_result
                and case_two_health["body"].get("version") == "v2.8.1"
                and case_two_health["body"].get("pool_size") == 1
            )

            print("CASE 3 — approved unmapped action")
            case_three = run_execute(make_state("restart affected pods", True))
            print(case_three.execution_result)
            passed.append(case_three.execution_result["status"] == "not_executable")
        finally:
            client.post(f"{base_url}/reset")

    print("PASS" if all(passed) and len(passed) == 3 else "FAIL")


if __name__ == "__main__":
    main()
