"""LLM classification and the replaceable live-evidence seam."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.agents.investigator import agentic_investigation
from backend.agents.llm_client import LLMClient
from backend.agents.mcp_client import call_mcp_tool
from backend.infra.db import query
from backend.schemas.alert import Alert

TRIAGE_PROMPT_PATH = Path(__file__).with_name("prompts") / "triage_system.md"


def deterministic_snapshot(alert: Alert, signature: str) -> dict:
    """Return a small, predictable MCP evidence snapshot even without tool calling."""
    escaped_signature = signature.replace("'", "''")
    statement = f"SELECT a.action, a.result, a.created_at FROM defaultdb.public.attempts a JOIN defaultdb.public.incidents i ON a.incident_id = i.id WHERE i.signature = '{escaped_signature}' ORDER BY a.created_at DESC LIMIT 5".strip()
    try:
        result = asyncio.run(
            call_mcp_tool(
                "select_query",
                {"database": "defaultdb", "query": statement},
            )
        )
    except Exception:
        result = {}
    rows = result.get("rows", result.get("data", []))
    return {
        "source": "deterministic",
        "tool": "select_query",
        "recent_attempts": rows if isinstance(rows, list) else [],
        "service": alert.service,
    }


def get_live_evidence(alert: Alert, signature: str) -> dict:
    # SEAM: agentic MCP investigation with deterministic floor.
    try:
        evidence = agentic_investigation(alert, signature)
        if evidence and evidence.get("findings") and evidence.get("tool_calls_made"):
            return evidence
    except Exception:
        pass
    return deterministic_snapshot(alert, signature)


def classify_alert(alert: Alert) -> str:
    prompt = TRIAGE_PROMPT_PATH.read_text(encoding="utf-8")
    content = json.dumps(alert.model_dump(), default=str)
    return LLMClient().complete(prompt, content).strip()
