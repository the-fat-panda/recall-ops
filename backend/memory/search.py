"""Vector retrieval over previously recorded operational incidents."""

from __future__ import annotations

import json
from typing import Any

from backend.infra.db import query
from backend.ingestion.embedder import embed


def search_incidents(alert_description: str, limit: int = 5) -> list[dict[str, Any]]:
    """Return nearest incidents and a normalized L2-derived similarity score."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    vector_literal = json.dumps(embed(alert_description, is_query=True), separators=(",", ","))
    rows = query(
        """
        SELECT id, signature, description, environment, created_at,
               embedding <-> %s::VECTOR AS l2_distance
        FROM incidents
        ORDER BY embedding <-> %s::VECTOR
        LIMIT %s
        """,
        (vector_literal, vector_literal, limit),
    )
    for row in rows:
        # Stored and query BGE vectors are normalized; their L2 distance is [0, 2].
        row["similarity"] = max(0.0, 1.0 - float(row.pop("l2_distance")) / 2.0)
    return rows
