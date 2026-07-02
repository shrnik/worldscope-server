"""Camera list sources.

Ported from the old TypeScript `getImages()` (src/api/downloadAllImages.ts) and
`getFaaImages()` (src/utils/get-faa-images.ts). Builds the combined list of camera
snapshots to embed: a Google Sheet plus FAA, USGS VolcView, and AlertWest cameras.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx

from app.settings import settings

FAA_API_URL = "https://weathercams.faa.gov/api/redistributable/sites"
VOLCVIEW_API_URL = "https://volcview.wr.usgs.gov/ashcam-api/webcamApi/webcams"
# Sheet rows tagged with this source are dropped in favor of the live API above.
VOLCVIEW_SOURCE = "https://volcview.wr.usgs.gov/ashcam-api/webcamApi/"
ALERTWEST_API_URL = "https://alertwest.live/api/getCameraDataByLoc"
ALERTWEST_IMG_BASE = "https://img.cdn.prod.alertwest.com/data/img"
ALERTWEST_SOURCE = "alertwest.live"


def get_sheet_images() -> list[dict[str, Any]]:
    """Fetch camera metadata rows from the Google Sheet (non-FAA sources)."""
    res = httpx.get(settings.sheet_url, timeout=30)
    res.raise_for_status()
    values: list[list[str]] = res.json()["values"]
    rows = values[1:]  # drop header

    cameras: list[dict[str, Any]] = []
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
    """Fetch FAA weather camera snapshots, one entry per camera."""
    if not settings.faa_api_key:
        return []
    res = httpx.get(
        FAA_API_URL,
        headers={"Authorization": f"Bearer {settings.faa_api_key}"},
        timeout=30,
    )
    res.raise_for_status()
    sites = res.json().get("payload", []) or []

    cameras: list[dict[str, Any]] = []
    for site in sites:
        for camera in site.get("cameras", []) or []:
            cameras.append(
                {
                    "camera_id": None,  # assigned below
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
    """Fetch USGS VolcView ashcam snapshots, one entry per imaged webcam."""
    res = httpx.get(VOLCVIEW_API_URL, timeout=30)
    res.raise_for_status()
    webcams = res.json().get("webcams", []) or []

    cameras: list[dict[str, Any]] = []
    for cam in webcams:
        url = cam.get("currentImageUrl")
        if not url:  # only webcams with a live snapshot
            continue
        cameras.append(
            {
                "camera_id": None,  # assigned below
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
    """Build the CDN image URL for an AlertWest camera.

    The path is data/img/<cid>/<yyyy>/<mm>/<dd>/<img>; the date is taken from
    the 10-digit Unix epoch embedded in the screenshot filename (`img`).
    """
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
    """Fetch AlertWest public camera snapshots, one entry per online camera.

    The API returns cameras (`cams`) linked to locations (`locs`) via `lid`.
    Offline cameras and those without a screenshot are skipped.
    """
    res = httpx.get(ALERTWEST_API_URL, timeout=60)
    res.raise_for_status()
    data = res.json().get("data") or {}
    cams = (data.get("cams") or {}).get("data") or []
    locs = {loc["id"]: loc for loc in (data.get("locs") or {}).get("data") or []}

    cameras: list[dict[str, Any]] = []
    for cam in cams:
        if cam.get("off") == 1:  # offline: no fresh snapshot
            continue
        if (cam.get("pr") or "").upper() == "FAA":  # FAA cams: see get_faa_images()
            continue
        url = _alertwest_image_url(cam)
        if not url:
            continue
        loc = locs.get(cam.get("lid")) or {}
        cameras.append(
            {
                "camera_id": None,  # assigned below
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
    """Combined camera list with stable, unique camera_ids."""
    sheet = get_sheet_images()
    faa = get_faa_images()
    volcview = get_volcview_images()
    alertwest = get_alertwest_images()
    for i, cam in enumerate(faa):
        cam["camera_id"] = f"faa-{i}"
    for i, cam in enumerate(volcview):
        cam["camera_id"] = f"volcview-{i}"
    for i, cam in enumerate(alertwest):
        cam["camera_id"] = f"alertwest-{i}"
    cameras = [*sheet, *faa, *volcview, *alertwest]
    return [c for c in cameras if c.get("url")]
