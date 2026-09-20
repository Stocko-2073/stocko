# A2 — soil surface and height above soil

Fits the datum surface to A1's float depth and emits `height_above_soil`.

**The datum is the straw mulch, not bare soil.** Bare soil is barely visible in
`plants.jpeg`; what the depth sees, and what this surface is fitted to, is the
top of the mulch. Every height here is offset from height-above-soil by the
straw depth, which one photograph cannot measure.

Everything is `scale_free`, in **rdu** (1 rdu = median scene depth of the source
raster). No metric claim anywhere.

## Rebuild

```bash
cd <repo>/models/plant_segmentation
V=chunks/A1/.venv/bin/python          # A1's venv: python 3.11, numpy 2.4.6, scipy 1.17.1
$V chunks/A2/fit_soil_surface.py --product primary_raster      # ~6 min
$V chunks/A2/fit_soil_surface.py --product primary_geometry    # ~4 min, the cross-check
$V chunks/A2/figures.py --tag primary_raster
$V chunks/A2/material_check.py
$V chunks/A2/occlusion_report.py
$V chunks/A2/compare_products.py
$V -m pytest chunks/A2/test_soil_fit.py -q
```

No new dependencies: A1's venv already had numpy, scipy, matplotlib and pillow.

## Files

| File | Role |
|---|---|
| `soil_fit.py` | The machinery: RANSAC plane with a geometrically-fixed normal orientation, penalised tensor-product B-spline (`PSpline2D`) with bisquare IRLS, empirical variogram, and the two cross-validation fold designs. Scene-agnostic; every constant is passed in. |
| `fit_soil_surface.py` | The pipeline. Reads A1's `products/MANIFEST.json`, back-projects with A1's `depth_to_cloud`, extends A1's local-planarity curve to the window A2 fits over, runs the outer loop, measures the gap-fill error curve, sweeps the two conventions, and writes the products. |
| `figures.py` | Height-band overlay, zooms, coverage, diagnostics. |
| `material_check.py` | The by-eye check written down: hand-placed material boxes, the height ordering they produce, PASS/MISMATCH. |
| `occlusion_report.py` | What the surface does where the canopy hides the ground. |
| `compare_products.py` | The same fit on both A1 depth products, and how far apart they land. |
| `a2_api.py` | **What A3 / A4 / A5 should import.** Loads the rasters with the datum caveat and the scale flag attached; `height_in_sigma()` and `confident_above(k)` are the scale-free ways to use it. |
| `test_soil_fit.py` | 18 tests. The load-bearing ones are the synthetic curved garden with known heights, and the check that a level-ground assumption would have failed it. |
| `products/` | Fitted on `primary_raster` — **the product to use.** |
| `products_primary_geometry/` | The same fit on the res-504 product, kept as the independent check. |
| `results/` | Reports, figures, logs. |

## Products (`products/`, 1344x1008, aligned to the A1 depth raster)

| File | Contents |
|---|---|
| `height_above_soil.npy` | float32 rdu above the datum, along the **local** surface normal |
| `height_above_soil_plane_normal.npy` | the same along the global RANSAC plane normal (they differ by 0.027 rdu rms ≈ 5σ — the surface is genuinely curved) |
| `validity_mask.npy` | bool |
| `coverage_class.npy` | 0 observed · 1 interpolated · 2 extrapolated |
| `support_distance_px.npy` | px to the nearest ground observation |
| `height_sigma.npy` | 1σ datum uncertainty, from the **measured** gap-fill curve |
| `ground_inliers.npy` | the pixels the surface was fitted to |
| `soil_surface_depth.npy` | z-depth of the datum along each ray |
| `soil_surface_plane_offset.npy` | datum minus the RANSAC plane |
| `A2_MANIFEST.json` | provenance, the datum warning, and every headline number |

Map to `plants.jpeg` (3000x4000) by resampling; `a2_api.load_a2(grid="image")`
does it.
