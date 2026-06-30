"""Camera list sources.

Ported from the old TypeScript `getImages()` (src/api/downloadAllImages.ts) and
`getFaaImages()` (src/utils/get-faa-images.ts). Builds the combined list of camera
snapshots to embed: rows from a Google Sheet plus FAA weather cameras.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.settings import settings

FAA_API_URL = "https://weathercams.faa.gov/api/redistributable/sites"


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
    return [c for c in cameras if c["source"] != "faa.gov"]


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


def get_all_cameras() -> list[dict[str, Any]]:
    """Combined camera list with stable, unique camera_ids."""
    sheet = get_sheet_images()
    faa = get_faa_images()
    for i, cam in enumerate(faa):
        cam["camera_id"] = f"faa-{i}"
    cameras = [*sheet, *faa]
    return [c for c in cameras if c.get("url")]
