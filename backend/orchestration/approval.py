"""Phase 4/5 seam for approving an interrupted run before resuming it."""

from __future__ import annotations


def approve_and_resume(graph, config):
    """Persist approval on an interrupted thread, then continue that same thread."""
    graph.update_state(config, {"approved": True})
    return graph.invoke(None, config)
