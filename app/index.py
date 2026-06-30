"""In-memory vector index.

Replaces Postgres/pgvector. Holds all image embeddings as a single numpy matrix and
does brute-force cosine search. At ~10k x 512 floats (~20 MB) this is sub-millisecond,
so no vector database is needed.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

import numpy as np
import pandas as pd

from app import hf_jobs

logger = logging.getLogger(__name__)

# Embeddings are stored L2-normalized so a dot product equals cosine similarity.
_embeddings: np.ndarray = np.empty((0, 512), dtype=np.float32)
_meta: list[dict[str, Any]] = []
_lock = threading.Lock()

_META_COLUMNS = ["camera_id", "url", "metadata", "ts"]


def _parse_parquet(path: str) -> tuple[np.ndarray, list[dict[str, Any]]]:
    df = pd.read_parquet(path)
    if df.empty:
        return np.empty((0, 512), dtype=np.float32), []

    embeddings = np.vstack(df["embedding"].to_numpy()).astype(np.float32)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    embeddings = embeddings / norms

    meta = [
        {col: row.get(col) for col in _META_COLUMNS}
        for row in df.to_dict(orient="records")
    ]
    # metadata is stored as a JSON string by the download job; parse it back.
    for row in meta:
        if isinstance(row.get("metadata"), str):
            try:
                row["metadata"] = json.loads(row["metadata"])
            except json.JSONDecodeError:
                pass

    # Integrity guard: the embedding matrix and metadata must stay row-aligned.
    if embeddings.shape[0] != len(meta):
        raise ValueError(
            f"embeddings/meta row mismatch: {embeddings.shape[0]} vs {len(meta)}"
        )
    return embeddings, meta


def load() -> None:
    """Download the embeddings file from the bucket and swap it into memory.

    Tolerates a missing file (e.g. before the first job has ever run).
    """
    try:
        path = hf_jobs.download_embeddings()
        embeddings, meta = _parse_parquet(path)
    except Exception as exc:  # noqa: BLE001 - missing/corrupt file: keep current index
        logger.warning("Could not load embeddings, keeping current index: %s", exc)
        return
    swap(embeddings, meta)
    logger.info("Loaded %d embeddings into memory", len(meta))


def swap(embeddings: np.ndarray, meta: list[dict[str, Any]]) -> None:
    """Atomically replace the in-memory index."""
    global _embeddings, _meta
    with _lock:
        _embeddings = embeddings
        _meta = meta


def count() -> int:
    return len(_meta)


def search(text_vec: np.ndarray, k: int = 50) -> list[dict[str, Any]]:
    """Return the top-k records by cosine similarity to a (normalized) query vector."""
    with _lock:
        embeddings = _embeddings
        meta = _meta

    if len(meta) == 0:
        return []

    scores = embeddings @ text_vec.astype(np.float32)
    k = min(k, len(meta))
    # argpartition for top-k, then sort that slice descending.
    top_idx = np.argpartition(-scores, k - 1)[:k]
    top_idx = top_idx[np.argsort(-scores[top_idx])]

    return [{**meta[i], "score": float(scores[i])} for i in top_idx]
