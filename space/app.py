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
from datetime import datetime, timezone

import gradio as gr
import httpx
import numpy as np
import pandas as pd
import plotly.express as px
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
        md = md or {}
        # Typed lat/lon columns exist in newer parquets; fall back to the
        # metadata JSON for files written before they were added.
        lat = _coord(row.get("lat"), md.get("lat"))
        lon = _coord(row.get("lon"), md.get("lon"))
        meta.append(
            {"url": row.get("url"), "metadata": md, "ts": row.get("ts"), "lat": lat, "lon": lon}
        )
    _meta = meta
    return f"Loaded {len(_meta)} images"


def _coord(*candidates) -> float | None:
    for value in candidates:
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if not np.isnan(value):
            return value
    return None


def search(query: str):
    if not query.strip():
        return [], gr.skip(), gr.skip()
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
        results.append((m["url"], f"{name} · {_fmt_ts(m.get('ts'))} · {scores[i]:.2f}"))
    fig, points = map_figure(scores)
    return results, fig, points


def map_points(scores: np.ndarray) -> list[dict]:
    """One entry per camera with known coordinates, in the order they are plotted."""
    return [
        {
            "lat": m["lat"],
            "lon": m["lon"],
            "similarity": float(scores[i]),
            "camera": (m["metadata"].get("camera_name") or "camera").strip(),
            "url": m["url"],
            "ts": m.get("ts"),
        }
        for i, m in enumerate(_meta)
        if m["lat"] is not None and m["lon"] is not None
    ]


def map_figure(scores: np.ndarray):
    """Plot every camera with known coordinates, colored by similarity to the query."""
    points = map_points(scores)
    if not points:
        return None, []
    df = pd.DataFrame(points)
    fig = px.scatter_map(
        df,
        lat="lat",
        lon="lon",
        color="similarity",
        hover_name="camera",
        color_continuous_scale="Viridis",
        zoom=2,
        height=600,
    )
    fig.update_traces(marker={"size": 8})
    fig.update_layout(margin={"l": 0, "r": 0, "t": 0, "b": 0})
    return fig, points


def show_camera(points: list[dict], evt: gr.SelectData):
    """Show the snapshot for the map dot the user clicked."""
    idx = evt.index
    if isinstance(idx, (list, tuple)):  # plotly reports (trace, point) in some versions
        idx = idx[-1]
    if not points or idx is None or not (0 <= idx < len(points)):
        return gr.skip(), gr.skip()
    p = points[idx]
    caption = f"**{p['camera']}** · {_fmt_ts(p['ts'])} · similarity {p['similarity']:.2f}"
    return p["url"], caption


def _fmt_ts(ts) -> str:
    """Render the snapshot timestamp as a relative 'time ago' string."""
    if not ts:
        return "—"
    try:
        when = datetime.fromisoformat(str(ts))
    except ValueError:
        return str(ts)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    seconds = (datetime.now(timezone.utc) - when).total_seconds()
    if seconds < 0:
        return "just now"
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{int(seconds // size)}{unit} ago"
    return "just now"


# --- UI ----------------------------------------------------------------------
with gr.Blocks(title="Worldscope Search") as demo:
    gr.Markdown("# 🌎 Worldscope\nSearch live-camera snapshots by describing what you want to see.")
    with gr.Row():
        query = gr.Textbox(
            label="Search", placeholder="e.g. snowy mountains, airport runway, foggy coastline", scale=4
        )
        btn = gr.Button("Search", variant="primary", scale=1)
    status = gr.Markdown()
    points_state = gr.State([])
    with gr.Row():
        map_plot = gr.Plot(label="Camera map (color = similarity, click a dot to preview)", scale=2)
        with gr.Column(scale=1):
            selected_image = gr.Image(label="Selected camera", height=400, interactive=False)
            selected_caption = gr.Markdown("*Click a dot on the map to see its snapshot.*")
    gallery = gr.Gallery(label="Results", columns=4, height=700, object_fit="cover")

    def startup():
        msg = load_index()
        fig, points = map_figure(np.zeros(len(_meta), dtype=np.float32))
        return msg, fig, points

    btn.click(search, inputs=query, outputs=[gallery, map_plot, points_state])
    query.submit(search, inputs=query, outputs=[gallery, map_plot, points_state])
    map_plot.select(show_camera, inputs=points_state, outputs=[selected_image, selected_caption])
    demo.load(startup, outputs=[status, map_plot, points_state])


if __name__ == "__main__":
    demo.launch()
