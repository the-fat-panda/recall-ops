"""FastAPI surface for starting and approving durable RecallOps runs."""

from __future__ import annotations

import uuid
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import httpx2
from langchain_cockroachdb import CockroachDBSaver
from pydantic import BaseModel

from backend.infra.db import database_url, query
from backend.orchestration.approval import approve_and_resume
from backend.orchestration.graph import build_graph
from backend.orchestration.config import orders_api_url
from backend.orchestration.state import AgentState
from backend.schemas.alert import Alert

app = FastAPI(title="RecallOps agent API")
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
def ask(request: AskRequest) -> StreamingResponse:
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    def event_stream():
        try:
            with CockroachDBSaver.from_conn_string(database_url()) as checkpointer:
                checkpointer.setup()
                graph = build_graph(checkpointer)
                for update in graph.stream(
                    AgentState(alert=request.alert, run_id=thread_id),
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
def reset() -> dict:
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
def approve(request: ApproveRequest) -> dict:
    config = {"configurable": {"thread_id": request.thread_id}}
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
        "thread_id": request.thread_id,
        "execution_result": state.execution_result,
        "outcome": state.outcome,
        "card": _card(state),
        "stats": _latest_stats(state),
    }
