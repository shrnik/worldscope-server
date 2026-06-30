---
title: Worldscope Search
emoji: 🌎
colorFrom: blue
colorTo: green
sdk: gradio
app_file: app.py
pinned: false
short_description: Semantic search over live-camera snapshots with CLIP
---

# Worldscope Search

Semantic image search over a bucket of live-camera snapshots. Type a description and
CLIP ranks the snapshots by similarity. Embeddings are precomputed by the HF Jobs
pipeline and stored in a public storage bucket; this Space loads them and searches
in memory.

## Configuration (Space variables)

- `HF_BUCKET` — bucket holding `embeddings.parquet` (default `shrnik/worldscope`)
- `EMBEDDINGS_PATH` — file name in the bucket (default `embeddings.parquet`)
- `CLIP_MODEL` — must match the embed job (default `openai/clip-vit-base-patch16`)
- `TOP_K` — number of results (default `100`)
