# PROBE — throwaway, proves CockroachDBSaver persists to CockroachDB. Run live.

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langchain_cockroachdb import CockroachDBSaver

from backend.infra.db import database_url


class ProbeState(TypedDict):
    counter: int


def node_a(_: ProbeState) -> dict[str, int]:
    return {"counter": 1}


def node_b(state: ProbeState) -> dict[str, int]:
    return {"counter": state["counter"] + 1}


builder = StateGraph(ProbeState)
builder.add_node("a", node_a)
builder.add_node("b", node_b)
builder.add_edge(START, "a")
builder.add_edge("a", "b")
builder.add_edge("b", END)


def main() -> None:
    config = {"configurable": {"thread_id": "recallops-checkpointer-probe"}}
    # CockroachDBSaver.from_conn_string() is the documented sync checkpointer factory.
    with CockroachDBSaver.from_conn_string(database_url()) as checkpointer:
        checkpointer.setup()
        graph = builder.compile(checkpointer=checkpointer)
        graph.invoke({}, config)
        persisted = graph.get_state(config).values.get("counter") == 2
    print(f"Persisted state reloaded as counter=2: {persisted}")


if __name__ == "__main__":
    main()
