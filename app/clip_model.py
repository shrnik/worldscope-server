"""CLIP model wrapper.

Loads `openai/clip-vit-base-patch16` once and embeds text queries into the 512-dim
space. The HF embed job (`jobs/embed_job.py`) embeds images with the same checkpoint,
so text queries and image embeddings are directly comparable.
"""

from __future__ import annotations

import numpy as np
import torch
from transformers import CLIPModel, CLIPProcessor

from app.settings import settings

_model: CLIPModel | None = None
_processor: CLIPProcessor | None = None
_device = "cuda" if torch.cuda.is_available() else "cpu"


def load() -> None:
    """Load the model + processor into memory. Idempotent."""
    global _model, _processor
    if _model is not None:
        return
    _model = CLIPModel.from_pretrained(settings.clip_model).to(_device).eval()
    _processor = CLIPProcessor.from_pretrained(settings.clip_model)


def _ensure_loaded() -> tuple[CLIPModel, CLIPProcessor]:
    if _model is None or _processor is None:
        load()
    assert _model is not None and _processor is not None
    return _model, _processor


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


@torch.inference_mode()
def embed_text(text: str) -> np.ndarray:
    """Return an L2-normalized 512-dim embedding for a text query."""
    model, processor = _ensure_loaded()
    inputs = processor(
        text=[text], return_tensors="pt", padding=True, truncation=True
    ).to(_device)
    features = model.get_text_features(**inputs)
    # transformers v5 returns an output object (pooler_output is the projected
    # embedding); v4 returns the tensor directly.
    if not torch.is_tensor(features):
        features = features.pooler_output
    vec = features.cpu().numpy().astype(np.float32)[0]
    return _l2_normalize(vec[None, :])[0]
