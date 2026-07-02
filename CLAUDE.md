# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                          # install deps (Python >=3.12, uv-managed, package = false)
cp .env.example .env             # fill in HF_TOKEN, HF_BUCKET, FAA_API_KEY
uv run uvicorn app.main:app      # run the FastAPI server locally
```

Pipeline stages can be run individually (each submits an HF Job and blocks until it finishes; needs `HF_TOKEN` with a Pro/Team account):

```bash
PYTHONPATH=. uv run python scripts/download_images.py    # CPU job: snapshots -> bucket + manifest
PYTHONPATH=. uv run python scripts/refresh_embeddings.py # GPU job: manifest -> embeddings.parquet
PYTHONPATH=. uv run python scripts/cleanup_images.py     # CPU job: prune unreferenced images
PYTHONPATH=. uv run python scripts/deploy_space.py       # upload space/ to the HF Space
```

There is no test suite or linter configured.

## Architecture

Semantic search over ~15k live camera snapshots using CLIP. Compute runs on **Hugging Face Jobs**, artifacts live in a public **HF storage bucket** (`hf://buckets/<ns>/worldscope`), and search happens **in memory** — deliberately no database, queue, or workers (this replaced a Node/Express + BullMQ + Postgres stack).

Data flow: `download job (CPU)` writes snapshots + `manifest.parquet` to the bucket → `embed job (GPU)` reads the manifest and writes `embeddings.parquet` → `cleanup job (CPU)` prunes images not referenced by the embeddings → the server/Space loads `embeddings.parquet` into a numpy matrix and does brute-force cosine search (~15k × 512-dim, sub-millisecond).

Three independent deployables share the bucket:

- **`app/`** — FastAPI server. `main.py` holds the refresh pipeline state machine (lock-guarded, deduplicated `POST /refresh` runs download → embed → index reload in a background thread). `index.py` is the in-memory index; embeddings are stored L2-normalized so dot product = cosine. `hf_jobs.py` wraps `huggingface_hub.run_uv_job` to submit jobs and build bucket URLs.
- **`jobs/`** — standalone HF Job scripts with PEP 723 inline dependencies (`# /// script` headers), executed remotely via `run_uv_job` with the bucket volume-mounted at `/bucket` (override `BUCKET_DIR` to run one locally). They do not import from `app/`.
- **`space/`** — self-contained Gradio frontend deployed as a HF Space; duplicates the load/search logic because it can't depend on `app/`.

`scripts/` are thin CI entrypoints, one per pipeline stage; they import from `app/` and therefore need `PYTHONPATH=.`.

## Cross-cutting constraints

- The CLIP checkpoint (`CLIP_MODEL`, default `openai/clip-vit-base-patch16`) must be the same in the server, `jobs/embed_job.py`, and `space/app.py` — image and text embeddings must share one space.
- `jobs/*.py` and `space/app.py` declare their own dependencies (inline script metadata / `space/requirements.txt`), separate from `pyproject.toml`. Adding an import to one of those files means updating its own dependency list, not the project's.
- Config comes from `app/settings.py` (pydantic-settings, reads `.env`); jobs receive their config as env vars passed through `app/hf_jobs.py` — a new setting typically needs to be threaded through both.
- Camera sources are duplicated across `app/cameras.py` (reads `settings`) and `jobs/download_job.py` (reads env vars, since `jobs/` can't import `app/`) — keep the two in sync. Each source is a `get_*_images()` function returning `{camera_id, camera_name, url, source, lat, lon, refresh_rate}`; `get_all_cameras()` merges the Google Sheet with the FAA, USGS VolcView, and AlertWest APIs and assigns stable id prefixes (`faa-`, `volcview-`, `alertwest-`). Rows are dropped from the sheet by their `source` tag for any source also pulled live, so a camera isn't listed twice. Only FAA needs a key (threaded via `hf_jobs.py`); VolcView/AlertWest are public and hardcoded like `FAA_API_URL`.
- GitHub Actions: `refresh-embeddings.yml` runs the three stages sequentially on demand (`workflow_dispatch`); `deploy-space.yml` deploys the Space on pushes to `main` touching `space/**`. Runners only orchestrate — real compute is the HF Job each script submits.
