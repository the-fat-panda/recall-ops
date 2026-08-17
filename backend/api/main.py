"""FastAPI surface for starting and approving durable RecallOps runs."""

from __future__ import annotations

import uuid
import json
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import httpx2
from langchain_cockroachdb import CockroachDBSaver
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.infra.db import database_url, query
from backend.orchestration.approval import approve_and_resume
from backend.orchestration.graph import build_graph
from backend.orchestration.config import orders_api_url
from backend.orchestration.state import AgentState
from backend.schemas.alert import Alert


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_client_ip)
RECALLOPS_ACCESS_KEY = os.getenv("RECALLOPS_ACCESS_KEY")

app = FastAPI(title="RecallOps agent API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    alert: Alert


class ApproveRequest(BaseModel):
    thread_id: str


def require_access_key(request: Request) -> None:
    if RECALLOPS_ACCESS_KEY and request.headers.get("X-API-Key") != RECALLOPS_ACCESS_KEY:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def _card(state: AgentState) -> dict | None:
    return state.experience_card.model_dump(mode="json") if state.experience_card else None


def _latest_stats(state: AgentState) -> dict | None:
    if state.chosen is None:
        return None
    rows = query(
        """
        SELECT success_count, fail_count, last_success_at, last_env_version
        FROM fix_stats WHERE signature = %s AND action = %s
        """,
        (state.signature, state.chosen.action),
    )
    return rows[0] if rows else None


def _sse_event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n"


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask")
@limiter.limit("15/minute")
def ask(
    request: Request,
    payload: AskRequest,
    _: None = Depends(require_access_key),
) -> StreamingResponse:
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    def event_stream():
        try:
            with CockroachDBSaver.from_conn_string(database_url()) as checkpointer:
                checkpointer.setup()
                graph = build_graph(checkpointer)
                for update in graph.stream(
                    AgentState(alert=payload.alert, run_id=thread_id),
                    config,
                    stream_mode="updates",
                ):
                    for node_name in update:
                        yield _sse_event(
                            "stage",
                            {"node": node_name, "thread_id": thread_id},
                        )
                state = AgentState.model_validate(graph.get_state(config).values)
            yield _sse_event(
                "result",
                {
                    "thread_id": thread_id,
                    "card": _card(state),
                    "outcome": state.outcome,
                },
            )
        except Exception as exc:
            yield _sse_event(
                "error",
                {"message": f"{type(exc).__name__}: {str(exc)[:200]}"},
            )
        yield _sse_event("done", {})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/reset")
@limiter.limit("30/minute")
def reset(
    request: Request,
    _: None = Depends(require_access_key),
) -> dict:
    try:
        with httpx2.Client(timeout=10.0) as client:
            response = client.post(f"{orders_api_url()}/reset")
        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Sandbox reset failed with HTTP {response.status_code}: {response.text[:200]}",
            )
        return {"reset": True, "sandbox": response.json()}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Sandbox reset failed: {type(exc).__name__}: {str(exc)[:200]}",
        ) from exc


@app.post("/approve")
@limiter.limit("30/minute")
def approve(
    request: Request,
    payload: ApproveRequest,
    _: None = Depends(require_access_key),
) -> dict:
    config = {"configurable": {"thread_id": payload.thread_id}}
    with CockroachDBSaver.from_conn_string(database_url()) as checkpointer:
        checkpointer.setup()
        graph = build_graph(checkpointer)
        snapshot = graph.get_state(config)
        if not snapshot.values:
            raise HTTPException(status_code=404, detail="Unknown thread_id.")
        if snapshot.next != ("execute",):
            raise HTTPException(
                status_code=409,
                detail="Thread is not awaiting approval.",
            )
        approve_and_resume(graph, config)
        state = AgentState.model_validate(graph.get_state(config).values)
    return {
        "thread_id": payload.thread_id,
        "execution_result": state.execution_result,
        "outcome": state.outcome,
        "card": _card(state),
        "stats": _latest_stats(state),
    }
