# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "httpx",
#   "pillow",
#   "pandas",
#   "pyarrow",
# ]
# ///
"""HF Job (CPU): download camera snapshots to the bucket and write a manifest.

This is the first of two jobs. It does the network-bound work (fetch camera list,
download images) on cheap CPU hardware, then the GPU embed job (jobs/embed_job.py)
reads the manifest and computes embeddings. Splitting avoids paying GPU rates while
downloading.

Steps:
  1. Build the camera list (Google Sheet + FAA, VolcView, and AlertWest APIs).
  2. Download each snapshot to /bucket/images/<camera_id>/<ts>.jpg (bounded concurrency).
  3. Write /bucket/<MANIFEST_PATH> (parquet) with one row per successfully downloaded image.

The storage bucket is mounted read+write at /bucket.
"""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import io
import json
import os
from typing import Any

import httpx
import pandas as pd
from PIL import Image

# /bucket on HF (volume mount); override BUCKET_DIR to run the job locally.
BUCKET = os.environ.get("BUCKET_DIR", "/bucket")
IMAGES_DIR = os.path.join(BUCKET, "images")
MANIFEST_PATH = os.path.join(BUCKET, os.environ.get("MANIFEST_PATH", "manifest.parquet"))
HF_BUCKET = os.environ.get("HF_BUCKET", "")
HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://huggingface.co")
SHEET_URL = os.environ["SHEET_URL"]
FAA_API_KEY = os.environ.get("FAA_API_KEY", "")
FAA_API_URL = "https://weathercams.faa.gov/api/redistributable/sites"
VOLCVIEW_API_URL = "https://volcview.wr.usgs.gov/ashcam-api/webcamApi/webcams"
VOLCVIEW_SOURCE = "https://volcview.wr.usgs.gov/ashcam-api/webcamApi/"
ALERTWEST_API_URL = "https://alertwest.live/api/getCameraDataByLoc"
ALERTWEST_IMG_BASE = "https://img.cdn.prod.alertwest.com/data/img"
ALERTWEST_SOURCE = "alertwest.live"

DOWNLOAD_CONCURRENCY = 16
# 0 = no cap; otherwise process at most this many cameras (useful for test runs).
MAX_IMAGES = int(os.environ.get("MAX_IMAGES", "0"))


def get_sheet_images() -> list[dict[str, Any]]:
    res = httpx.get(SHEET_URL, timeout=60)
    res.raise_for_status()
    rows = res.json()["values"][1:]
    cameras = []
    for index, row in enumerate(rows):
        cameras.append(
            {
                "camera_id": str(index),
                "url": row[1] if len(row) > 1 else None,
                "camera_name": row[0] if len(row) > 0 else None,
                "source": row[2] if len(row) > 2 else None,
                "lat": row[3] if len(row) > 3 else None,
                "lon": row[4] if len(row) > 4 else None,
                "refresh_rate": row[5] if len(row) > 5 else None,
            }
        )
    excluded = {"faa.gov", VOLCVIEW_SOURCE, ALERTWEST_SOURCE}
    return [c for c in cameras if c["source"] not in excluded]


def get_faa_images() -> list[dict[str, Any]]:
    if not FAA_API_KEY:
        return []
    res = httpx.get(
        FAA_API_URL, headers={"Authorization": f"Bearer {FAA_API_KEY}"}, timeout=120
    )
    res.raise_for_status()
    sites = res.json().get("payload", []) or []
    cameras = []
    for site in sites:
        for camera in site.get("cameras", []) or []:
            cameras.append(
                {
                    "camera_id": None,
                    "camera_name": (
                        f"{site.get('siteName', '')} "
                        f"{camera.get('cameraDirection', '')} "
                        f"{site.get('operatedBy', '') or ''}"
                    ).strip(),
                    "url": camera.get("currentImageUri"),
                    "source": "faa.gov",
                    "lat": site.get("latitude"),
                    "lon": site.get("longitude"),
                    "refresh_rate": "10 min",
                }
            )
    return cameras


def get_volcview_images() -> list[dict[str, Any]]:
    res = httpx.get(VOLCVIEW_API_URL, timeout=60)
    res.raise_for_status()
    webcams = res.json().get("webcams", []) or []
    cameras = []
    for cam in webcams:
        url = cam.get("currentImageUrl")
        if not url:
            continue
        cameras.append(
            {
                "camera_id": None,
                "camera_name": cam.get("webcamName"),
                "url": url,
                "source": VOLCVIEW_SOURCE,
                "lat": cam.get("latitude"),
                "lon": cam.get("longitude"),
                "refresh_rate": "10 min",
            }
        )
    return cameras


def _alertwest_image_url(cam: dict[str, Any]) -> str | None:
    # data/img/<cid>/<yyyy>/<mm>/<dd>/<img>; date from the epoch embedded in img.
    cid, img = cam.get("id"), cam.get("img")
    if not cid or not img:
        return None
    stem = img[:-4] if img.lower().endswith(".jpg") else img
    epoch = next(
        (
            int(tok)
            for tok in reversed(stem.split("_"))
            if tok.isdigit() and 1_000_000_000 <= int(tok) <= 2_000_000_000
        ),
        None,
    )
    if epoch is None:
        return None
    d = dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
    return f"{ALERTWEST_IMG_BASE}/{cid}/{d.year}/{d.month:02d}/{d.day:02d}/{img}"


def get_alertwest_images() -> list[dict[str, Any]]:
    res = httpx.get(ALERTWEST_API_URL, timeout=60)
    res.raise_for_status()
    data = res.json().get("data") or {}
    cams = (data.get("cams") or {}).get("data") or []
    locs = {loc["id"]: loc for loc in (data.get("locs") or {}).get("data") or []}
    cameras = []
    for cam in cams:
        if cam.get("off") == 1:
            continue
        if (cam.get("pr") or "").upper() == "FAA":  # FAA cams: see get_faa_images()
            continue
        url = _alertwest_image_url(cam)
        if not url:
            continue
        loc = locs.get(cam.get("lid")) or {}
        cameras.append(
            {
                "camera_id": None,
                "camera_name": cam.get("cn"),
                "url": url,
                "source": ALERTWEST_SOURCE,
                "lat": loc.get("lat"),
                "lon": loc.get("lon"),
                "refresh_rate": "1 min",
            }
        )
    return cameras


def get_all_cameras() -> list[dict[str, Any]]:
    # Isolate sources: a slow/failing source shouldn't abort the whole run.
    try:
        sheet = get_sheet_images()
    except Exception as exc:  # noqa: BLE001
        print(f"sheet source failed: {exc}")
        sheet = []
    try:
        faa = get_faa_images()
    except Exception as exc:  # noqa: BLE001
        print(f"FAA source failed: {exc}")
        faa = []
    try:
        volcview = get_volcview_images()
    except Exception as exc:  # noqa: BLE001
        print(f"VolcView source failed: {exc}")
        volcview = []
    try:
        alertwest = get_alertwest_images()
    except Exception as exc:  # noqa: BLE001
        print(f"AlertWest source failed: {exc}")
        alertwest = []
    for i, cam in enumerate(faa):
        cam["camera_id"] = f"faa-{i}"
    for i, cam in enumerate(volcview):
        cam["camera_id"] = f"volcview-{i}"
    for i, cam in enumerate(alertwest):
        cam["camera_id"] = f"alertwest-{i}"
    print(
        f"cameras: {len(sheet)} from sheet, {len(faa)} from FAA, "
        f"{len(volcview)} from VolcView, {len(alertwest)} from AlertWest"
    )
    return [c for c in [*sheet, *faa, *volcview, *alertwest] if c.get("url")]


def download_one(camera: dict[str, Any], ts_iso: str, ts_file: str) -> dict[str, Any] | None:
    """Download a snapshot to the bucket; return a manifest row, or None on failure."""
    try:
        res = httpx.get(camera["url"], timeout=30, follow_redirects=True)
        res.raise_for_status()
        image = Image.open(io.BytesIO(res.content)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        print(f"failed to download {camera['camera_id']}: {exc}")
        return None

    image_path = f"images/{camera['camera_id']}/{ts_file}.jpg"
    abs_path = os.path.join(BUCKET, image_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    image.save(abs_path, format="JPEG")

    return {
        "camera_id": camera["camera_id"],
        "url": f"{HF_ENDPOINT}/buckets/{HF_BUCKET}/resolve/{image_path}",
        "image_path": image_path,
        # JSON string (not a struct) so heterogeneous types across sources
        # (e.g. str vs float lat/lon) don't break parquet schema inference.
        "metadata": json.dumps(
            {
                "camera_name": camera.get("camera_name"),
                "source": camera.get("source"),
                "lat": camera.get("lat"),
                "lon": camera.get("lon"),
                "refresh_rate": camera.get("refresh_rate"),
            }
        ),
        "ts": ts_iso,
    }


def main() -> None:
    cameras = get_all_cameras()
    if MAX_IMAGES:
        cameras = cameras[:MAX_IMAGES]
    print(f"{len(cameras)} cameras to download")

    now = dt.datetime.now(dt.timezone.utc)
    ts_iso = now.isoformat()
    ts_file = now.strftime("%Y%m%dT%H%M%SZ")
    os.makedirs(IMAGES_DIR, exist_ok=True)

    rows: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=DOWNLOAD_CONCURRENCY) as pool:
        for result in pool.map(lambda c: download_one(c, ts_iso, ts_file), cameras):
            if result is not None:
                rows.append(result)
    print(f"{len(rows)} images downloaded")

    df = pd.DataFrame(rows)
    tmp_path = MANIFEST_PATH + ".tmp"
    df.to_parquet(tmp_path, index=False)
    os.replace(tmp_path, MANIFEST_PATH)
    print(f"wrote manifest with {len(df)} rows to {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
