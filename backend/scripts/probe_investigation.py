# PROBE — throwaway. Tests agentic MCP investigation + fallback. Run live.

from backend.agents.triage import get_live_evidence
from backend.schemas.alert import Alert


def main() -> None:
    alert = Alert(
        service="orders-api",
        symptom="pods restarting repeatedly, back-off restarting failed container",
        meta={},
    )
    evidence = get_live_evidence(alert, "CrashLoopBackOff")
    print(f"source: {evidence['source']}")
    if "tool_calls_made" in evidence:
        print(f"tool_calls_made: {evidence['tool_calls_made']}")
    if "findings" in evidence:
        print(f"findings: {evidence['findings']}")
    else:
        print(f"recent_attempts: {evidence['recent_attempts']}")


if __name__ == "__main__":
    main()
