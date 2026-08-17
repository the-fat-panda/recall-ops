"""Deterministic Phase 3 node functions. No LangGraph or LLM calls live here."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

import httpx2

from backend.ingestion.embedder import embed
from backend.infra.db import query
from backend.agents.recommend import run_recommend
from backend.agents.triage import get_live_evidence, classify_alert
from backend.memory.scoring import confidence, freshness
from backend.memory.search import search_incidents
from backend.orchestration.config import get_config, orders_api_url
from backend.orchestration.state import AgentState
from backend.schemas.candidate import IncidentMatch, ScoredAction

EXECUTORS = {
    # Action name -> sandbox executor endpoint. One executor is installed for the
    # prototype; unregistered actions route to their production runbook executor.
    "rollback deployment to prior revision": "/rollback",
}


def run_memory_search(state: AgentState) -> AgentState:
    config = get_config()
    rows = search_incidents(state.alert.symptom, limit=config["memory"]["top_k"])
    state.matches = [IncidentMatch(**row) for row in rows]
    state.match_count = len(state.matches)
    return state


def run_triage(state: AgentState) -> AgentState:
    state.signature = classify_alert(state.alert)
    state.live_evidence = get_live_evidence(state.alert, state.signature)
    return state


def run_reason(state: AgentState) -> AgentState:
    config = get_config()
    stats = query(
        """
        SELECT action, success_count, fail_count, last_success_at, last_env_version
        FROM fix_stats WHERE signature = %s
        """,
        (state.signature,),
    )
    candidates = [
        ScoredAction(
            action=row["action"],
            success_count=row["success_count"],
            fail_count=row["fail_count"],
            confidence=confidence(row["success_count"], row["fail_count"]),
            freshness=freshness(
                row["last_success_at"],
                row["last_env_version"],
                config["env"]["current_version"],
            ),
            last_success_at=row["last_success_at"],
            last_env_version=row["last_env_version"],
        )
        for row in stats
    ]
    state.candidates = candidates
    state.chosen = min(
        candidates,
        key=lambda candidate: (
            -candidate.confidence,
            -candidate.success_count,
            candidate.fail_count,
            candidate.action,
        ),
        default=None,
    )
    state.is_confident = (
        state.chosen is not None
        and state.chosen.confidence >= config["reason"]["min_confidence"]
    )
    if state.chosen is not None:
        if state.chosen.confidence >= config["confidence"]["high_threshold"]:
            state.confidence_band = "HIGH"
        elif state.chosen.confidence >= config["confidence"]["medium_threshold"]:
            state.confidence_band = "MEDIUM"
        else:
            state.confidence_band = "LOW"
    return state


def build_escalation(state: AgentState) -> AgentState:
    from backend.schemas.card import ExperienceCard

    state.outcome = "ESCALATED"
    state.confidence_band = "LOW"
    state.explanation = "no confident historical strategy"
    state.experience_card = ExperienceCard(
        signature=state.signature,
        match_summary=f"Searched {state.match_count} similar past incident(s).",
        live_evidence=state.live_evidence,
        candidates=state.candidates,
        chosen_action="",
        failed_history=[
            f"{candidate.action}: {candidate.fail_count} failed attempt(s)"
            for candidate in state.candidates
            if candidate.fail_count > 0
        ],
        confidence_band="LOW",
        explanation=state.explanation,
        outcome="ESCALATED",
    )
    return state


def _response_evidence(response: httpx2.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        body = {"text": response.text}
    return {"http_status": response.status_code, "body": body}


def run_execute(state: AgentState) -> AgentState:
    """Execute only approved, explicitly wired runbooks and verify the result."""
    action = state.chosen.action if state.chosen is not None else None
    state.writeback_done = False
    if state.approved is not True:
        state.execution_result = {"status": "not_approved", "action": action}
        return state

    endpoint = EXECUTORS.get(action)
    # No executor is registered for this action in the prototype. In production,
    # it routes to the matching runbook executor; approval and learning still apply.
    if endpoint is None:
        state.execution_result = {"status": "not_executable", "action": action}
        return state

    base_url = orders_api_url()
    try:
        with httpx2.Client(timeout=10.0) as client:
            rollback_response = _response_evidence(client.post(f"{base_url}{endpoint}"))
            health_response: dict | None = None
            health_checks = 0
            for health_checks in range(1, 4):
                health_response = _response_evidence(client.get(f"{base_url}/health", timeout=5.0))
                health_body = health_response.get("body", {})
                if (
                    health_response["http_status"] == 200
                    and health_body.get("version") == "v2.8.0"
                    and health_body.get("pool_size") == 20
                ):
                    break
                if health_checks < 3:
                    time.sleep(0.5)
    except Exception as exc:
        state.execution_result = {
            "status": "execution_error",
            "error": f"{type(exc).__name__}: {exc}",
            "action": action,
        }
        return state

    health_body = health_response.get("body", {}) if health_response else {}
    healed = (
        health_response is not None
        and health_response["http_status"] == 200
        and health_body.get("version") == "v2.8.0"
        and health_body.get("pool_size") == 20
    )
    state.execution_result = {
        "status": "executed",
        "result": "success" if rollback_response["http_status"] == 200 and healed else "fail",
        "action": action,
        "endpoint": endpoint,
        "rollback_response": rollback_response,
        "health_response": health_response,
        "health_checks": health_checks,
    }
    return state


def run_writeback(state: AgentState) -> AgentState:
    """Persist one completed execution as a live incident, attempt, and statistic."""
    result = state.execution_result or {}
    if result.get("status") != "executed":
        return state

    incident_id = uuid.uuid5(uuid.NAMESPACE_URL, f"recallops-incident:{state.run_id}")
    attempt_id = uuid.uuid5(uuid.NAMESPACE_URL, f"recallops-attempt:{state.run_id}")
    try:
        if query("SELECT 1 FROM attempts WHERE id = %s", (str(attempt_id),)):
            state.writeback_done = True
            return state

        action = state.chosen.action if state.chosen is not None else result["action"]
        outcome = result["result"]
        description = f"[LIVE] {state.alert.service}: {state.alert.symptom}"
        health_body = result.get("health_response", {}).get("body", {})
        environment = state.alert.meta.get("environment", "production-k8s")
        healed_version = health_body.get("version")
        now = datetime.now(timezone.utc)
        embedding = json.dumps(embed(description), separators=(",", ","))

        query(
            """
            INSERT INTO incidents (id, signature, description, embedding, environment, created_at)
            VALUES (%s, %s, %s, %s::VECTOR, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (str(incident_id), state.signature, description, embedding, str(environment), now),
        )
        query(
            """
            INSERT INTO attempts (id, incident_id, action, result, created_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (str(attempt_id), str(incident_id), action, outcome, now),
        )
        success_delta = 1 if outcome == "success" else 0
        fail_delta = 1 if outcome == "fail" else 0
        query(
            """
            INSERT INTO fix_stats (
                signature, action, success_count, fail_count, last_success_at, last_env_version
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (signature, action) DO UPDATE SET
                success_count = fix_stats.success_count + excluded.success_count,
                fail_count = fix_stats.fail_count + excluded.fail_count,
                last_success_at = CASE
                    WHEN excluded.success_count > 0 THEN excluded.last_success_at
                    ELSE fix_stats.last_success_at
                END,
                last_env_version = CASE
                    WHEN excluded.success_count > 0 THEN excluded.last_env_version
                    ELSE fix_stats.last_env_version
                END
            """,
            (
                state.signature,
                action,
                success_delta,
                fail_delta,
                now if success_delta else None,
                healed_version if success_delta else None,
            ),
        )
    except Exception as exc:
        print(f"[writeback failed] {type(exc).__name__}: {exc}")
        state.execution_result = {
            **result,
            "writeback_status": "error",
            "writeback_error": f"{type(exc).__name__}: {exc}",
        }
        state.writeback_done = False
        return state

    state.writeback_done = True
    return state
