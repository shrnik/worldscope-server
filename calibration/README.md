# Ground Camera Calibrator

Browser tool for geo-referencing fixed cameras: solves camera pose + intrinsics from
image↔map point pairs, with GeoCalib seeding, SAM3 segmentation, OSM context, and an
AI auto-calibration agent.

## Running

The page uses ES modules, so it must be served over HTTP (opening `index.html` via
`file://` will not work):

```bash
python -m http.server 8000   # from the repo root
```

Then open <http://localhost:8000/calibration/>.

Note: serving from a new host/port is a new browser origin — saved tokens and
autosaves from a previous origin (e.g. `file://`) do not carry over. Re-enter your
HF token in Settings once; use Export/Import project to move work across origins.

## Tokens

- **Hugging Face token** (Settings) — needed for GeoCalib/SAM3 Spaces and the VLM/agent.
- **Mapillary client token** (Settings) — optional, enables street-level photos;
  free at <https://www.mapillary.com/dashboard/developers>.

Both are stored only in your browser's localStorage.

## Layout

- `index.html` — UI, math (projection/homography/LM solver), canvas + Leaflet map, app state.
- `js/api/` — external service clients (GeoCalib, SAM3, Overpass, Wikipedia, HF VLM router, elevation, Mapillary). DOM-free; token/inputs passed in.
- `js/agent/` — agent tool schemas + executors, system prompts, pi-agent runner, visual-refine loop.
- `js/main.js` — bootstrap module; exposes everything to the page as `window.CalibExt`.

The AI "visual refine" loop works best with stronger vision models; small VLMs may
nudge parameters in the wrong direction (guardrails revert to the best-RMS snapshot).
