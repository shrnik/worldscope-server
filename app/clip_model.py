"""Text embedding model wrapper (filename is historical — the checkpoint is TIPS v2).

Loads `google/tipsv2-b14` once and embeds text queries into the 768-dim space. The
HF embed job (`jobs/embed_job.py`) embeds images with the same checkpoint, so text
queries and image embeddings are directly comparable.
"""

from __future__ import annotations

import numpy as np
import torch
from transformers import AutoModel

from app.settings import settings

_model: torch.nn.Module | None = None


def load() -> None:
    """Load the model into memory. Idempotent."""
    global _model
    if _model is not None:
        return
    _model = AutoModel.from_pretrained(settings.embed_model, trust_remote_code=True).eval()


def _ensure_loaded() -> torch.nn.Module:
    if _model is None:
        load()
    assert _model is not None
    return _model


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


@torch.inference_mode()
def embed_text(text: str) -> np.ndarray:
    """Return an L2-normalized embedding for a text query."""
    model = _ensure_loaded()
    # encode_text tokenizes internally and returns (1, dim).
    vec = model.encode_text([text]).cpu().numpy().astype(np.float32)[0]
    return _l2_normalize(vec[None, :])[0]
