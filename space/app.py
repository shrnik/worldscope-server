"""Worldscope semantic image search — Hugging Face Space (Gradio).

Self-contained search frontend:
  - loads the TIPS v2 text tower (same checkpoint the embed job used),
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
from transformers import AutoModel

HF_BUCKET = os.environ.get("HF_BUCKET", "shrnik/worldscope")
HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://huggingface.co")
EMBEDDINGS_PATH = os.environ.get("EMBEDDINGS_PATH", "embeddings.parquet")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "google/tipsv2-b14")
TOP_K = int(os.environ.get("TOP_K", "100"))

EMBEDDINGS_URL = f"{HF_ENDPOINT}/buckets/{HF_BUCKET}/resolve/{EMBEDDINGS_PATH}"

# --- model -------------------------------------------------------------------
_model = AutoModel.from_pretrained(EMBED_MODEL, trust_remote_code=True).eval()


@torch.inference_mode()
def embed_text(text: str) -> np.ndarray:
    # encode_text tokenizes internally and returns (1, dim).
    vec = _model.encode_text([text]).cpu().numpy().astype(np.float32)[0]
    norm = np.linalg.norm(vec) or 1.0
    return vec / norm


# --- index -------------------------------------------------------------------
_embeddings = np.empty((0, 768), dtype=np.float32)
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
        lat = _coord(row.get("lat"), md.get("lat"), bound=90)
        lon = _coord(row.get("lon"), md.get("lon"), bound=180)
        meta.append(
            {"url": row.get("url"), "metadata": md, "ts": row.get("ts"), "lat": lat, "lon": lon}
        )
    _meta = meta
    return f"Loaded {len(_meta)} images"


def _coord(*candidates, bound: float) -> float | None:
    for value in candidates:
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if not np.isnan(value) and abs(value) <= bound:
            return value
    return None


def search(query: str):
    if not query.strip():
        return [], None
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
    return results, map_figure(scores)


# Points backing the current map figure, in plot order, so a select event's
# index can be resolved back to a camera.
_points: list[dict] = []


def map_figure(scores: np.ndarray):
    """Plot every camera with known coordinates, colored by similarity to the query."""
    global _points
    _points = [
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
    if not _points:
        return None
    df = pd.DataFrame(_points)
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
    return fig


def on_point_click(idx_str: str):
    """Show the snapshot for the map dot the user clicked (index arrives via hidden textbox)."""
    try:
        idx = int(idx_str)
    except (TypeError, ValueError):
        return gr.skip(), gr.skip()
    if not (0 <= idx < len(_points)):
        return gr.skip(), gr.skip()
    p = _points[idx]
    caption = f"**{p['camera']}** · {_fmt_ts(p['ts'])} · similarity {p['similarity']:.2f}"
    return p["url"], caption


# gr.Plot has no .select event on the Gradio version the Space runs, so listen for
# plotly_click in the browser and relay the point index through a hidden textbox.
# The plot div is replaced on every re-render, so keep re-attaching via setInterval.
_PLOT_CLICK_JS = """
() => {
    const attach = () => {
        const plot = document.querySelector('#map_plot .js-plotly-plot');
        if (!plot || plot.dataset.clickBound) return;
        plot.dataset.clickBound = '1';
        plot.on('plotly_click', (data) => {
            const idx = data.points?.[0]?.pointIndex;
            if (idx === undefined) return;
            const box = document.querySelector('#selected_point textarea');
            if (!box) return;
            box.value = String(idx);
            box.dispatchEvent(new Event('input', { bubbles: true }));
        });
    };
    setInterval(attach, 500);
}
"""


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
    gallery = gr.Gallery(label="Results", columns=4, height=700, object_fit="cover")
    with gr.Row():
        map_plot = gr.Plot(
            label="Detections map (color = similarity, click a dot to preview)",
            scale=2,
            elem_id="map_plot",
        )
        with gr.Column(scale=1):
            selected_image = gr.Image(label="Selected camera", height=400, interactive=False)
            selected_caption = gr.Markdown("*Click a dot on the map to see its snapshot.*")
    selected_idx = gr.Textbox(visible=False, elem_id="selected_point")

    btn.click(search, inputs=query, outputs=[gallery, map_plot])
    query.submit(search, inputs=query, outputs=[gallery, map_plot])
    selected_idx.input(on_point_click, inputs=selected_idx, outputs=[selected_image, selected_caption])
    demo.load(load_index, outputs=status)
    demo.load(fn=None, js=_PLOT_CLICK_JS)


if __name__ == "__main__":
    demo.launch()
