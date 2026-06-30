"""Worldscope FastAPI server.

Serves semantic image search over an in-memory CLIP index, and triggers HF Jobs to
(re)compute image embeddings on demand. Replaces the old Node/Express + BullMQ +
Postgres stack.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from app import clip_model, hf_jobs, index
from app.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-flight refresh state, guarded by _refresh_lock so only one pipeline runs at a time.
_refresh_lock = threading.Lock()
_refresh_state: dict = {
    "active": False,
    "stage": "idle",  # idle | downloading | embedding | done | error
    "download_job_id": None,
    "embed_job_id": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
}


def _set_state(**kwargs) -> None:
    with _refresh_lock:
        _refresh_state.update(kwargs)


def _run_pipeline() -> None:
    """Run download -> embed -> reload index, updating refresh state as it goes."""
    try:
        download_id = hf_jobs.trigger_download_job()
        _set_state(stage="downloading", download_job_id=download_id)
        if hf_jobs.poll_until_done(download_id) != "COMPLETED":
            _set_state(stage="error", error=f"download job {download_id} failed")
            return
        embed_id = hf_jobs.trigger_embedding_job()
        _set_state(stage="embedding", embed_job_id=embed_id)
        if hf_jobs.poll_until_done(embed_id) != "COMPLETED":
            _set_state(stage="error", error=f"embed job {embed_id} failed")
            return
        index.load()
        _set_state(stage="done")
        logger.info("Index reloaded after refresh")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Refresh pipeline failed")
        _set_state(stage="error", error=str(exc))
    finally:
        _set_state(active=False, finished_at=dt.datetime.now(dt.timezone.utc).isoformat())


@asynccontextmanager
async def lifespan(app: FastAPI):
    clip_model.load()
    index.load()
    yield


app = FastAPI(title="Worldscope", lifespan=lifespan)


class TextEmbeddingRequest(BaseModel):
    text: str


@app.get("/")
def root():
    return {"message": "API - 👋🌎🌍🌏", "indexed": index.count()}


@app.get("/images")
def search_images(query: str = Query(...)):
    text_vec = clip_model.embed_text(query)
    return index.search(text_vec, k=settings.search_top_k)


@app.post("/embeddings/text")
def embed_text(req: TextEmbeddingRequest):
    return {"text": req.text, "embedding": clip_model.embed_text(req.text).tolist()}


@app.post("/refresh")
def refresh():
    """Start the download -> embed -> reload pipeline.

    Deduplicated: if a refresh is already running, returns 409 with its status
    instead of launching another pipeline.
    """
    with _refresh_lock:
        if _refresh_state["active"]:
            return JSONResponse(
                status_code=409,
                content={"message": "refresh already in progress", **_refresh_state},
            )
        _refresh_state.update(
            active=True,
            stage="starting",
            download_job_id=None,
            embed_job_id=None,
            error=None,
            started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            finished_at=None,
        )
        snapshot = dict(_refresh_state)
    threading.Thread(target=_run_pipeline, daemon=True).start()
    return {"message": "refresh started", **snapshot}


@app.get("/refresh")
def refresh_state():
    """Current refresh pipeline status."""
    with _refresh_lock:
        return dict(_refresh_state)


@app.get("/refresh/{job_id}")
def refresh_job_status(job_id: str):
    """Raw HF stage for a specific job id."""
    return {"job_id": job_id, "stage": hf_jobs.get_status(job_id)}


@app.get("/image/{path:path}")
def get_image(path: str):
    """Redirect to the image's direct URL in the public bucket."""
    return RedirectResponse(hf_jobs.bucket_image_url(path), status_code=307)
