"""Local, deterministic BGE embeddings for RecallOps Phase 1."""

from __future__ import annotations

from functools import lru_cache
from typing import Sequence

MODEL_NAME = "BAAI/bge-base-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME, device="cpu")


def embed(text: str, *, is_query: bool = False) -> list[float]:
    """Create one normalized 768-dimensional embedding on CPU.

    BGE's instruction is intentionally applied only to search queries, never to
    incident descriptions stored in the memory corpus.
    """
    value = f"{QUERY_PREFIX}{text}" if is_query else text
    return _model().encode(value, normalize_embeddings=True, show_progress_bar=False).tolist()


def embed_batch(texts: Sequence[str], *, is_query: bool = False) -> list[list[float]]:
    """Create normalized embeddings while preserving input order."""
    values = [f"{QUERY_PREFIX}{text}" if is_query else text for text in texts]
    if not values:
        return []
    return _model().encode(values, normalize_embeddings=True, show_progress_bar=False).tolist()
