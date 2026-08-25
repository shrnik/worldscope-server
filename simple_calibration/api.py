"""Simple point-picking calibration API.

Serves a click-to-calibrate UI (index.html) and a /calibrate endpoint that
solves camera pose + intrinsics from image<->GPS point pairs using
utils.projection_utils (same solver/reprojection as the contrails api.py).

Run from the repo root:

    uv run python simple_calibration/api.py            # http://localhost:8001
"""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import datetime
import json
import os
import re
import tempfile

import cv2
import httpx
import numpy as np
import uvicorn
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from utils.projection_utils import (
    calculate_fov_from_intrinsics,
    ecef_to_enu,
    estimate_camera_params,
    gps_to_camxy_vasha_fixed,
    gps_to_ecef,
)

app = FastAPI(title="Simple Calibration")

# The UI is a standalone HTML file that may be opened via file:// or another
# port, so the API must accept cross-origin calls.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

IMAGES_DIR = Path(__file__).parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


@app.get("/images_list")
def images_list():
    return sorted(
        p.name for p in IMAGES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )


GEOCALIB_SPACE = "https://shrnik-geocalib.hf.space"
_geocalib_client = None


def _hf_token() -> str | None:
    if os.environ.get("HF_TOKEN"):
        return os.environ["HF_TOKEN"]
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip().startswith("HF_TOKEN="):
                return line.split("=", 1)[1].strip().strip("'\"") or None
    return None

DEFAULT_HFOV_GUESSES = [15, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110]


class Gps(BaseModel):
    lat: float
    lon: float
    alt: float


class PointPair(BaseModel):
    x: float
    y: float
    lat: float
    lon: float
    alt: float
    use: bool = True  # excluded points are still reprojected, just not fitted


class CalibrationRequest(BaseModel):
    camera: Gps
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    points: list[PointPair] = Field(min_length=4)
    hfov_guesses: list[float] | None = None
    k1_seed: float | None = None  # GeoCalib simple_radial k1, used to seed distortion


def pan_tilt_roll(r_matrix: np.ndarray) -> tuple[float, float, float]:
    """Decompose an ENU->camera rotation into pan (deg CW from north),
    tilt (deg above horizon) and roll (deg, right side up = 0)."""
    fwd = r_matrix.T @ np.array([0.0, 0.0, 1.0])
    right = r_matrix.T @ np.array([1.0, 0.0, 0.0])
    pan = math.degrees(math.atan2(fwd[0], fwd[1]))
    tilt = math.degrees(math.atan2(fwd[2], math.hypot(fwd[0], fwd[1])))
    horizon_right = np.cross(fwd, [0.0, 0.0, 1.0])
    horizon_right /= np.linalg.norm(horizon_right)
    roll = math.degrees(math.atan2(float(right @ [0.0, 0.0, 1.0]), float(right @ horizon_right)))
    return pan, tilt, roll


MAX_CAMERA_DRIFT_M = 300.0  # reject refinements that move the known camera further


def _kabsch(cam_rays: np.ndarray, world_dirs: np.ndarray) -> np.ndarray:
    """Closed-form rotation R minimizing ||cam_rays - R @ world_dirs|| (Wahba)."""
    hmat = cam_rays.T @ world_dirs
    u, _, vt = np.linalg.svd(hmat)
    d = np.sign(np.linalg.det(u @ vt))
    return u @ np.diag([1.0, 1.0, d]) @ vt


def _k_for_focal(focal: float, w: int, h: int) -> np.ndarray:
    return np.array([[focal, 0, w / 2], [0, focal, h / 2], [0, 0, 1]], dtype=np.float64)


def _pixel_rays(k_mat: np.ndarray, xy: np.ndarray, dist: np.ndarray | None = None) -> np.ndarray:
    if dist is None:
        rays = (np.linalg.inv(k_mat) @ np.column_stack([xy, np.ones(len(xy))]).T).T
    else:
        und = cv2.undistortPoints(xy.reshape(-1, 1, 2).astype(np.float64), k_mat, dist)
        rays = np.column_stack([und[:, 0, 0], und[:, 0, 1], np.ones(len(xy))])
    return rays / np.linalg.norm(rays, axis=1, keepdims=True)


def solve(req: CalibrationRequest) -> dict:
    origin_gps = [req.camera.lat, req.camera.lon, req.camera.alt]
    w, h = req.image_width, req.image_height

    poi_ecef = np.array([gps_to_ecef([p.lat, p.lon, p.alt]) for p in req.points])
    poi_xy = np.array([[p.x, p.y] for p in req.points], dtype=np.float64)
    lats = np.array([p.lat for p in req.points])
    lons = np.array([p.lon for p in req.points])
    alts = np.array([p.alt for p in req.points])
    poi_enu = ecef_to_enu(origin_gps, poi_ecef)
    world_dirs = poi_enu / np.linalg.norm(poi_enu, axis=1, keepdims=True)

    # fit on the included points only; excluded ones are reprojected at the end
    use = np.array([p.use for p in req.points], dtype=bool)
    if use.sum() < 4:
        raise HTTPException(422, f"Need at least 4 included points (have {int(use.sum())}).")
    poi_xy_f, world_dirs_f, poi_ecef_f = poi_xy[use], world_dirs[use], poi_ecef[use]
    lats_f, lons_f, alts_f = lats[use], lons[use], alts[use]

    def evaluate(k_mat, r_mat, t_vec, dist):
        est_x, est_y, _ = gps_to_camxy_vasha_fixed(
            lats_f, lons_f, alts_f, k_mat, r_mat, np.asarray(t_vec).reshape(3, 1),
            origin_gps, distortion=dist,
        )
        err = np.hypot(est_x - poi_xy_f[:, 0], est_y - poi_xy_f[:, 1])
        # A point that projects behind the camera / far outside the FOV comes
        # back NaN — treat that solution as bad rather than average survivors.
        if np.all(np.isnan(err)):
            return np.inf, est_x, est_y, err
        rms = float(np.sqrt(np.nanmean(err**2)))
        if np.any(np.isnan(err)):
            rms += 1e6
        return rms, est_x, est_y, err

    # --- Stage A: camera pinned at its known position (t = 0), rotation from
    # closed-form ray alignment, focal from a fine FOV grid. This cannot fall
    # into the focal/distance ambiguity that lets calibrateCamera "explain" a
    # narrow landmark spread as a telephoto shot from far away.
    t_zero = np.zeros((3, 1))

    def rot_only(hfov, k1=0.0):
        focal = 0.5 * w / math.tan(math.radians(hfov) / 2)
        k_mat = _k_for_focal(focal, w, h)
        dist = None if k1 == 0.0 else np.array([k1, 0, 0, 0, 0], dtype=np.float64)
        r_mat = _kabsch(_pixel_rays(k_mat, poi_xy_f, dist), world_dirs_f)
        rms, est_x, est_y, err = evaluate(k_mat, r_mat, t_zero, dist)
        return {"rms": rms, "k": k_mat,
                "dist": np.zeros((5, 1)) if dist is None else dist.reshape(5, 1),
                "r": r_mat, "t": t_zero, "est_x": est_x, "est_y": est_y,
                "err": err, "seed_hfov": hfov, "k1": k1}

    grid = list(np.arange(5.0, 121.0, 1.0)) + [
        g for g in (req.hfov_guesses or []) if 1.0 < g < 170.0
    ]
    k1_options = [0.0]
    if req.k1_seed:
        k1_options.append(req.k1_seed)
    best = min((rot_only(hfov, k1) for hfov in grid for k1 in k1_options),
               key=lambda c: c["rms"])
    # golden-section polish of the focal around the best grid cell
    lo, hi = best["seed_hfov"] - 1.5, best["seed_hfov"] + 1.5
    for _ in range(24):
        m1, m2 = lo + 0.382 * (hi - lo), lo + 0.618 * (hi - lo)
        if rot_only(m1, best["k1"])["rms"] < rot_only(m2, best["k1"])["rms"]:
            hi = m2
        else:
            lo = m1
    cand = rot_only((lo + hi) / 2, best["k1"])
    if cand["rms"] < best["rms"]:
        best = cand
    method, warnings = "rotation_only", []

    # --- Stage B: full calibrateCamera refinement (distortion + translation),
    # accepted only if it improves RMS without moving the known camera.
    try:
        rvec, _ = cv2.Rodrigues(best["r"])
        k_mat, dist, r_mat, t_vec, _ = estimate_camera_params(
            origin_gps, poi_ecef_f, poi_xy_f, (h, w),
            intrinsics_estimate=best["k"].astype(np.float32),
            distortion_estimate=best["dist"].astype(np.float32),
            rvecs=[rvec.astype(np.float32)],
            tvecs=[t_zero.astype(np.float32)],
        )
        rms, est_x, est_y, err = evaluate(k_mat, r_mat, t_vec, dist)
        drift = float(np.linalg.norm(-r_mat.T @ np.asarray(t_vec).reshape(3)))
        if drift > MAX_CAMERA_DRIFT_M:
            warnings.append(
                f"Full refinement moved the camera {drift/1000:.1f} km from its known "
                f"position (focal/distance ambiguity) — kept the fixed-position solution."
            )
        elif rms >= best["rms"]:
            warnings.append("Full refinement did not improve RMS — kept the fixed-position solution.")
        else:
            best = {"rms": rms, "k": k_mat, "dist": dist, "r": r_mat, "t": t_vec,
                    "est_x": est_x, "est_y": est_y, "err": err,
                    "seed_hfov": best["seed_hfov"]}
            method = "full_refine"
    except cv2.error:
        warnings.append(
            "Full refinement not possible (too few points for the distortion model) "
            "— kept the fixed-position solution."
        )

    if not np.isfinite(best["rms"]):
        raise HTTPException(422, "Calibration failed — check that the points are correct and not collinear.")
    if (best["rms"] % 1e6) > 10:
        warnings.append(
            "High RMS — likely a mislabeled landmark; check the per-point errors "
            "and try unchecking the worst point."
        )

    # reproject ALL points (excluded ones too) with the final model for feedback
    est_x_all, est_y_all, _ = gps_to_camxy_vasha_fixed(
        lats, lons, alts, best["k"], best["r"],
        np.asarray(best["t"]).reshape(3, 1), origin_gps, distortion=best["dist"],
    )
    err_all = np.hypot(est_x_all - poi_xy[:, 0], est_y_all - poi_xy[:, 1])

    hfov, vfov = calculate_fov_from_intrinsics(best["k"], w, h, distortion=best["dist"])
    pan, tilt, roll = pan_tilt_roll(best["r"])
    cam_enu = (-best["r"].T @ np.asarray(best["t"]).reshape(3)).tolist()

    def clean(v):
        return None if (v is None or not np.isfinite(v)) else float(v)

    return {
        "rms_px": clean(best["rms"] if best["rms"] < 1e6 else best["rms"] - 1e6),
        "method": method,
        "warnings": warnings,
        "seed_hfov_deg": best["seed_hfov"],
        "hfov_deg": hfov,
        "vfov_deg": vfov,
        "focal_px": float(best["k"][0, 0]),
        "pan_deg": pan,
        "tilt_deg": tilt,
        "roll_deg": roll,
        "camera_offset_enu_m": cam_enu,
        "points": [
            {
                "x": p.x, "y": p.y, "used": p.use,
                "est_x": clean(est_x_all[i]),
                "est_y": clean(est_y_all[i]),
                "error_px": clean(err_all[i]),
            }
            for i, p in enumerate(req.points)
        ],
        # Same shape utils.projection_utils.load_camera_parameters reads back.
        "camera_params": {
            "intrinsics": best["k"].tolist(),
            "distortion": np.asarray(best["dist"]).ravel().tolist(),
            "rotation": best["r"].tolist(),
            "translation": np.asarray(best["t"]).ravel().tolist(),
            "origin_gps": {"lat": req.camera.lat, "lon": req.camera.lon, "alt": req.camera.alt},
        },
    }


@app.post("/calibrate")
def calibrate(req: CalibrationRequest):
    return solve(req)


def _parse_geocalib_text(raw: str) -> dict:
    """Pull numbers out of the Space's free-text result (mirrors
    calibration/js/api/geocalib.js parseGeoCalibText)."""

    def num(label):
        m = re.search(label + r"[^\-\d]{0,12}(-?\d+(?:\.\d+)?)", raw, re.IGNORECASE)
        return float(m.group(1)) if m else None

    return {
        "focal_px": num("focal"),
        "vfov_deg": num(r"v[ _-]?fov") or num(r"\bfov"),
        "roll_deg": num("roll"),
        "pitch_deg": num("pitch"),
        "k1": num("k1"),
    }


@app.post("/geocalib")
def geocalib(image: UploadFile):
    """Neural single-image estimate of focal/roll/pitch/k1 via the GeoCalib
    Space — used to seed the FOV before /calibrate, like the contrails API."""
    global _geocalib_client
    try:
        from gradio_client import Client, handle_file
    except ImportError:
        raise HTTPException(500, "gradio_client is not installed — run `uv sync` (it is in the dev group).")

    suffix = Path(image.filename or "img.jpg").suffix or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(image.file.read())
        tmp_path = tmp.name
    try:
        if _geocalib_client is None:
            _geocalib_client = Client(
                GEOCALIB_SPACE, token=_hf_token(),
                httpx_kwargs={"timeout": httpx.Timeout(300, connect=30)},
            )
        result = _geocalib_client.predict(
            handle_file(tmp_path),
            "simple_radial",
            False, False, False, False, False,
            api_name="/process_results",
        )
    except Exception as e:
        _geocalib_client = None
        raise HTTPException(502, f"GeoCalib call failed: {e}")
    finally:
        os.unlink(tmp_path)

    raw = " ".join(str(part) for part in (result if isinstance(result, (list, tuple)) else [result]))
    parsed = _parse_geocalib_text(raw)
    if parsed["focal_px"] is None and parsed["vfov_deg"] is None:
        raise HTTPException(502, f"Could not parse GeoCalib output: {raw[:500]}")
    parsed["raw"] = raw[:2000]
    return parsed


@app.get("/proxy")
async def proxy(url: str):
    """Fetch a camera image server-side so hotlink/CORS-restricted URLs still load."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            r = await client.get(url)
            r.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Could not fetch image: {e}")
    return Response(content=r.content, media_type=r.headers.get("content-type", "image/jpeg"))


@app.post("/export")
def export_bundle(
    name: str = Form(...),
    camera_params: str = Form(...),
    points: str = Form(...),
    image: UploadFile | None = None,
    original: UploadFile | None = None,
):
    """Write a per-camera export folder: solved params, point pairs, and the
    annotated image (points + reprojections + horizon) rendered by the UI."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-") or "camera"
    out = Path(__file__).parent / "exports" / safe
    previous = None
    # never destroy an earlier export: move it aside before writing
    if out.exists() and any(out.iterdir()):
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        trash = out.parent / ".trash" / f"{safe}-{stamp}"
        trash.parent.mkdir(parents=True, exist_ok=True)
        out.rename(trash)
        previous = str(trash)
    out.mkdir(parents=True, exist_ok=True)
    try:
        (out / "camera_params.json").write_text(json.dumps(json.loads(camera_params), indent=2))
        (out / "calibration_points.json").write_text(json.dumps(json.loads(points), indent=2))
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"Invalid JSON payload: {e}")
    files = ["camera_params.json", "calibration_points.json"]
    if image is not None:
        (out / f"{safe}_annotated.jpg").write_bytes(image.file.read())
        files.append(f"{safe}_annotated.jpg")
    if original is not None:
        # untouched source frame, so the calibration can be reproduced exactly
        ext = Path(original.filename or "").suffix.lower() or ".jpg"
        (out / f"{safe}_original{ext}").write_bytes(original.file.read())
        files.append(f"{safe}_original{ext}")
    return {"path": str(out), "files": files, "previous_backup": previous}


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "index.html")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
