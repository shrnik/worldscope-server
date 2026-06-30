"""HF Jobs orchestration via the huggingface_hub Python API.

Triggers the two-stage pipeline (CPU download job -> GPU embed job), polls jobs to
completion, and downloads artifacts (the embeddings parquet) from the storage bucket.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time

from huggingface_hub import (
    Volume,
    download_bucket_files,
    inspect_job,
    run_uv_job,
)

from app.settings import settings

logger = logging.getLogger(__name__)

# Fall back to the CLI login token (~/.cache/huggingface) when HF_TOKEN is unset.
_TOKEN = settings.hf_token or None

_JOBS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "jobs")
_DOWNLOAD_SCRIPT = os.path.join(_JOBS_DIR, "download_job.py")
_EMBED_SCRIPT = os.path.join(_JOBS_DIR, "embed_job.py")

_TERMINAL_STAGES = {"COMPLETED", "ERROR", "CANCELED", "DELETED"}


def _bucket_volume() -> Volume:
    return Volume(type="bucket", source=settings.hf_bucket, mount_path="/bucket")


def trigger_download_job() -> str:
    """Launch the CPU download job (fetch camera list + images -> bucket + manifest)."""
    job = run_uv_job(
        _DOWNLOAD_SCRIPT,
        flavor=settings.hf_download_flavor,
        timeout=settings.hf_job_timeout,
        volumes=[_bucket_volume()],
        secrets={"FAA_API_KEY": settings.faa_api_key},
        env={
            "SHEET_URL": settings.sheet_url,
            "MANIFEST_PATH": settings.manifest_path,
            "HF_BUCKET": settings.hf_bucket,
            "HF_ENDPOINT": settings.hf_endpoint,
        },
        token=_TOKEN,
    )
    logger.info("Triggered download job %s (%s)", job.id, job.url)
    return job.id


def trigger_embedding_job() -> str:
    """Launch the GPU embed job (manifest + images -> embeddings parquet)."""
    job = run_uv_job(
        _EMBED_SCRIPT,
        flavor=settings.hf_embed_flavor,
        timeout=settings.hf_job_timeout,
        volumes=[_bucket_volume()],
        env={
            "CLIP_MODEL": settings.clip_model,
            "MANIFEST_PATH": settings.manifest_path,
            "EMBEDDINGS_PATH": settings.embeddings_path,
        },
        token=_TOKEN,
    )
    logger.info("Triggered embedding job %s (%s)", job.id, job.url)
    return job.id


def get_status(job_id: str) -> str:
    """Return the current job stage (e.g. RUNNING, COMPLETED, ERROR)."""
    return inspect_job(job_id=job_id, token=_TOKEN).status.stage


def poll_until_done(job_id: str, interval: float = 15.0) -> str:
    """Block until the job reaches a terminal stage; return that stage."""
    while True:
        stage = get_status(job_id)
        if stage in _TERMINAL_STAGES:
            logger.info("Job %s finished with stage %s", job_id, stage)
            return stage
        time.sleep(interval)


def download_embeddings() -> str:
    """Download the embeddings parquet from the bucket. Returns the local path."""
    local_path = os.path.join(tempfile.gettempdir(), "worldscope_embeddings.parquet")
    download_bucket_files(
        settings.hf_bucket,
        files=[(settings.embeddings_path, local_path)],
        token=_TOKEN,
    )
    return local_path


def _to_relative_path(path: str) -> str:
    """Reduce a stored image URL to a path relative to the bucket root.

    The index stores full `hf://buckets/<ns>/<bucket>/images/...` URLs; the bucket
    download API expects the path within the bucket (e.g. `images/...`).
    """
    prefix = f"hf://buckets/{settings.hf_bucket}/"
    if path.startswith(prefix):
        return path[len(prefix) :]
    if path.startswith("hf://buckets/"):
        # Fall back to dropping the "hf://buckets/<ns>/<bucket>/" prefix generically.
        return path[len("hf://buckets/") :].split("/", 2)[-1]
    return path


def bucket_image_url(stored_url: str) -> str:
    """Return the direct public HTTPS URL for an image in the (public) bucket.

    Accepts either a relative path (`images/...`) or a full `hf://buckets/...` URI.
    """
    rel = _to_relative_path(stored_url)
    return f"{settings.hf_endpoint}/buckets/{settings.hf_bucket}/resolve/{rel}"
