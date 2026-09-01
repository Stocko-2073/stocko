# Progress

Status table is the single source of truth for *where we are*.
The log below it is **append-only** — add entries at the bottom, never edit or
tidy earlier ones. The reasoning in old entries is the point.

Statuses: `not started` · `in progress` · `blocked` · `done`

## Status

| Chunk | Title | Depends on | Status | Findings |
|---|---|---|---|---|
| A0 | Ground truth for one image | — | not started | |
| A1 | Real depth and honest geometry | — | not started | |
| A1b | Assumed intrinsics, bounded rather than hidden | A1 | not started | |
| A2 | Soil surface and height above soil | A1 | not started | |
| A3 | Plant material segmentation | A0, A2 | not started | |
| A4 | Grouping by connectivity, not distance | A2, A3 | not started | |
| A5 | Stem-soil contact points | A2, A4 | not started | |
| A6 | Keep-out volumes | A4 | not started | |
| A7 | VLM instance labelling | A4 | not started | |
| A8 | MCP tool surface and the safety gate | A5, A6, A7 | not started | |
| B1 | Generalisation beyond one image | A8 + image set | blocked | needs 20–50 photos to protocol |
| B2 | Auto-labelling and a fast model | B1 | blocked | needs B1 |
| C0 | Calibrate the robot camera | robot camera | blocked | needs hardware |
| C1 | Multi-view and active re-observation | C0 + mobile base | blocked | needs hardware |
| C2 | Persistent garden map | C1 | blocked | needs hardware |
| C3 | Actuator selection and precision budget | candidate tools | blocked | needs hardware |
| C4 | Closed-loop targeting and verification | C3 + arm | blocked | needs hardware |

**Next up:** A0, then A1. A0 first because without ground truth every later
chunk degenerates into eyeballing overlays.

---

## Log

### 001 — 2026-08-30 → 2026-09-01 · Baseline trial and roadmap

**Chunk:** none (pre-roadmap exploration)

**Done**
- Ported ZeroPlantSeg to Apple Silicon and ran it end-to-end on `plants.jpeg`.
  Rebuilt on torch 2.2.2 + MPS under Python 3.11; added `zps_device.py` to
  route the hardcoded `.cuda()` calls; cast sample points to float32 in
  segment-anything's `automatic_mask_generator.py` (MPS has no float64).
- Found `ckpt_download.sh` serves the wrong file: its Google Drive link returns
  the full 2.0 GB OVSeg model, not the CLIP checkpoint the code loads.
  Extracted the 446 `clip_adapter.clip_model.*` tensors into the 1.7 GB
  `ovseg_clip_l_9a1909.pth` the code expects — size match confirms it.
- Fixed a latent bug in `get_leaf_root_wls`: `calc_leaf_keypoints` has three
  return shapes and one silently unpacked a single coordinate into two scalars,
  corrupting the clustering.
- Swept DBSCAN `eps` and added `recluster.py` to re-run clustering from cached
  keypoints in seconds.
- Authored `RESEARCH_ROADMAP.md`; scaffolded tracking (this file,
  `CONSTANTS.md`, `RESULTS.md`, `chunks/`, `/goal`).

**Measured** — see `RESULTS.md` for the recorded baseline.

**Decided**
- Do not build on leaf-root distance clustering. The `eps` window is narrow
  (100 isolates the clover, 130 swallows it) and the published configs hard-code
  it per dataset *and* capture date. Group by observed 3D connectivity against a
  measured soil surface instead.
- ZeroPlantSeg's likely long-term role is offline auto-labeller (B2), not
  runtime. Explicit kill decision deferred until A4 lands.
- Adopted rules R1–R4. R1 gained category (d) once it became clear the camera
  for `plants.jpeg` is unavailable and intrinsics must be assumed.

**Surprised us**
- Depth Anything V3 resolves individual petioles as continuous 3D structures
  radiating from the crown. That is what makes connectivity-based grouping (A4)
  plausible at all, and it was the part I was least confident about.
- The photo has no EXIF and came from a third party, so calibration is
  impossible. Absolute scale is unresolvable for this image and Phase A is
  written to be scale-free as a result.

**Next**
- A0: hand-label `plants.jpeg` and ship `eval.py`.
