"""Worldscope semantic image search — Hugging Face Space (Gradio).

Self-contained search frontend:
  - loads the CLIP text model (same checkpoint the embed job used),
  - pulls embeddings.parquet from the public storage bucket,
  - does brute-force cosine search in memory,
  - shows the matching camera snapshots (served via the bucket's public URLs).
"""

from __future__ import annotations

import io
import json
import os

import gradio as gr
import httpx
import numpy as np
import pandas as pd
import torch
from transformers import CLIPModel, CLIPProcessor

HF_BUCKET = os.environ.get("HF_BUCKET", "shrnik/worldscope")
HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://huggingface.co")
EMBEDDINGS_PATH = os.environ.get("EMBEDDINGS_PATH", "embeddings.parquet")
CLIP_MODEL = os.environ.get("CLIP_MODEL", "openai/clip-vit-base-patch16")
TOP_K = int(os.environ.get("TOP_K", "100"))

EMBEDDINGS_URL = f"{HF_ENDPOINT}/buckets/{HF_BUCKET}/resolve/{EMBEDDINGS_PATH}"

# --- model -------------------------------------------------------------------
_model = CLIPModel.from_pretrained(CLIP_MODEL).eval()
_processor = CLIPProcessor.from_pretrained(CLIP_MODEL)


@torch.inference_mode()
def embed_text(text: str) -> np.ndarray:
    inputs = _processor(text=[text], return_tensors="pt", padding=True, truncation=True)
    out = _model.get_text_features(**inputs)
    feats = out if torch.is_tensor(out) else out.pooler_output  # v4 tensor / v5 object
    vec = feats.cpu().numpy().astype(np.float32)[0]
    norm = np.linalg.norm(vec) or 1.0
    return vec / norm


# --- index -------------------------------------------------------------------
_embeddings = np.empty((0, 512), dtype=np.float32)
_meta: list[dict] = []


def load_index() -> str:
    """Download the embeddings parquet from the public bucket and build the index."""
    global _embeddings, _meta
    res = httpx.get(EMBEDDINGS_URL, timeout=120, follow_redirects=True)
    res.raise_for_status()
    df = pd.read_parquet(io.BytesIO(res.content))

    emb = np.vstack(df["embedding"].to_numpy()).astype(np.float32)
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    _embeddings = emb / norms

    meta = []
    for row in df.to_dict(orient="records"):
        md = row.get("metadata")
        if isinstance(md, str):
            try:
                md = json.loads(md)
            except json.JSONDecodeError:
                md = {}
        meta.append({"url": row.get("url"), "metadata": md or {}, "ts": row.get("ts")})
    _meta = meta
    return f"Loaded {len(_meta)} images"


def search(query: str):
    if not query.strip():
        return []
    if not _meta:
        load_index()
    scores = _embeddings @ embed_text(query)
    k = min(TOP_K, len(_meta))
    top = np.argpartition(-scores, k - 1)[:k]
    top = top[np.argsort(-scores[top])]
    results = []
    for i in top:
        m = _meta[i]
        name = (m["metadata"].get("camera_name") or "camera").strip()
        results.append((m["url"], f"{name} · {scores[i]:.2f}"))
    return results


# --- UI ----------------------------------------------------------------------
with gr.Blocks(title="Worldscope Search") as demo:
    gr.Markdown("# 🌎 Worldscope\nSearch live-camera snapshots by describing what you want to see.")
    with gr.Row():
        query = gr.Textbox(
            label="Search", placeholder="e.g. snowy mountains, airport runway, foggy coastline", scale=4
        )
        btn = gr.Button("Search", variant="primary", scale=1)
    status = gr.Markdown()
    gallery = gr.Gallery(label="Results", columns=4, height=700, object_fit="cover")

    btn.click(search, inputs=query, outputs=gallery)
    query.submit(search, inputs=query, outputs=gallery)
    demo.load(load_index, outputs=status)


if __name__ == "__main__":
    demo.launch()
