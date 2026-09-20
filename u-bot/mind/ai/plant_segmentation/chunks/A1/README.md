# A1 — running it

`.venv/` (959 MB), `da3-src/` (an upstream clone) and `depth/*/*.npy` are not
committed. Everything needed to rebuild them is here.

## 1. Upstream code

```bash
cd chunks/A1
git clone https://github.com/ByteDance-Seed/depth-anything-3 da3-src
git -C da3-src checkout 3d835ec1a5802d64a8b8b15f817a1ab54809bfe4
```

No patch is needed. `da3_infer.py` adds `da3-src/src` to `sys.path` and stubs a
few optional imports rather than modifying upstream.

## 2. Environment

A dedicated venv, separate from `ZeroPlantSeg/.venv` — that one is pinned to
torch 2.2.2 / transformers 4.38.2 for GroundingDINO and must not be disturbed.

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.lock.txt
```

or, from scratch:

```bash
uv pip install --python .venv/bin/python torch torchvision numpy \
  opencv-python pillow einops addict huggingface_hub safetensors omegaconf \
  tqdm scipy matplotlib trimesh imageio evo plyfile pillow_heif pytest
```

Notes:

- DA3's `pyproject.toml` lists `xformers`, `gsplat`, `pycolmap`, `moviepy`,
  `open3d` and `e3nn`. None are on the single-image depth path and several have
  no arm64 macOS wheel, so `da3_infer.py` puts empty modules in `sys.modules`
  for them. If one were ever actually used we would get an `AttributeError`,
  not a wrong number.
- `evo`, `plyfile` and `pillow_heif` **are** imported for real and must be
  installed.
- DA3 asks for `numpy<2`; it runs fine on the 2.x that landed here. Recorded in
  `requirements.lock.txt`.
- MPS works throughout. `PYTORCH_ENABLE_MPS_FALLBACK=1` is set by the script.
  The depth and camera heads run under `torch.autocast(enabled=False)`, so they
  are fp32 regardless of the fp16 autocast around the backbone.

## 3. Weights

Pulled automatically from the Hub on first run (~11 GB total for all four).
Revisions used are recorded in every `depth/*/provenance.json`.

| Preset | Repo | Revision | Camera head? | Metric? |
|---|---|---|---|---|
| `da3-large` | `depth-anything/DA3-LARGE` | `c54c26b1` | yes | no |
| `da3metric-large` | `depth-anything/DA3METRIC-LARGE` | `4010e39f` | **no** | no (needs the nested wrapper) |
| `da3mono-large` | `depth-anything/DA3MONO-LARGE` | `f465978e` | **no** | no |
| `da3nested-giant-large` | `depth-anything/DA3NESTED-GIANT-LARGE-1.1` | `b2359bdf` | yes | yes |

## 4. Reproduce

```bash
export PYTORCH_ENABLE_MPS_FALLBACK=1

# depth rasters (16 runs, ~5 min once the weights are cached)
for r in 504 700 896 1120 1344 1680; do
  for m in da3-large da3nested-giant-large; do
    .venv/bin/python da3_infer.py --model $m --res $r
  done
done
for m in da3metric-large da3mono-large; do
  for r in 504 1344; do .venv/bin/python da3_infer.py --model $m --res $r; done
done

.venv/bin/python camera_report.py        # -> results/camera.json, fig_fov_vs_resolution.png
.venv/bin/python measure_quantisation.py # -> results/quantisation.json
.venv/bin/python compare_preview.py      # -> results/preview_vs_float.json + 3 figures
.venv/bin/python export_products.py      # -> products/MANIFEST.json + clouds
.venv/bin/python -m pytest -q test_depth_to_cloud.py
```

Inference is bit-for-bit deterministic on this machine (verified in
`camera_report.py`), so all of the above reproduces exactly.

## 5. What later chunks should read

`products/MANIFEST.json`. It names the two depth products, says which one has a
usable camera, carries the instrument constants, and states the scale claim.
Do not reach past it into `depth/` without reading the provenance JSON there.
