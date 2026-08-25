# Simple Calibration

Minimal click-to-calibrate tool: click points on a camera image, enter each
point's lat/lon/alt, set the camera origin, and get reprojection feedback
(green crosses + per-point pixel error) from a local solver — same flow as
[pless/contrails api.py](https://github.com/pless/contrails/blob/main/api.py),
reusing this repo's `utils/projection_utils.py` for all the math.

## Run

```bash
uv run python simple_calibration/api.py   # serves UI + API on http://127.0.0.1:8001
```

Open <http://127.0.0.1:8001/> — or open `index.html` directly as a file; it
calls the local server cross-origin (CORS is enabled).

## Endpoints

- `POST /calibrate` — `{camera: {lat,lon,alt}, image_width, image_height, points: [{x,y,lat,lon,alt}], hfov_guesses?}`.
  Seeds `cv2.solvePnP` over a grid of FOV guesses, refines with
  `utils.projection_utils.estimate_camera_params` (calibrateCamera, radial
  distortion), reprojects with `gps_to_camxy_vasha_fixed`, returns the
  best-RMS solution: per-point reprojections/errors, hfov/vfov, pan/tilt/roll,
  and a `camera_params` object in the exact shape
  `utils.projection_utils.load_camera_parameters` reads back.
- `POST /geocalib` — multipart image upload; calls the GeoCalib HF Space
  (`shrnik-geocalib`, needs `HF_TOKEN` in env or `.env`) for a neural
  focal/pitch/roll/k1 estimate, used by the UI to seed the solver.
- `GET /proxy?url=` — server-side image fetch so hotlink/CORS-restricted
  camera URLs load into the canvas.

## UI notes

- Camera origin (lat/lon/alt) is a separate input from the clicked points.
- Scroll = zoom, drag empty space = pan, click = add point, drag marker =
  move it, Delete key = remove selected point. ≥4 completed points required.
- State autosaves to localStorage; Export/Import moves a point set between
  browsers; "Download camera_params.json" saves the solved parameters.
