# Reproducing the ZeroPlantSeg port (Apple Silicon)

`ZeroPlantSeg/` is a separate upstream clone plus ~6.7 GB of model weights and a
1.1 GB venv, so it is **not** committed. This directory has everything needed to
rebuild it. Total download is around 5 GB.

Patched against upstream commit `8f3baa2f7beb8ed8b0c07b066a0ee1a82e32db81`
(https://github.com/JunhaoXing/ZeroPlantSeg).

## 1. Clone and apply the patch

```bash
cd models/plant_segmentation
git clone https://github.com/JunhaoXing/ZeroPlantSeg.git
cd ZeroPlantSeg
git checkout 8f3baa2f7beb8ed8b0c07b066a0ee1a82e32db81
git apply ../port/apple-silicon.patch
```

The patch covers: device routing via `zps_device.py`, the `.cuda()` calls in
OVSeg's predictor, removed `np.int`/`np.float`/`np.bool` deprecations,
GroundingDINO's device defaults, the `get_leaf_root_wls` return-shape fix, two
leftover debug prints, the `squash`/`squash2` configs and dataset registration,
`recluster.py`, and the `viz_*.py` figure scripts.

## 2. Environment

Upstream pins `torch 1.10.1+cu113`, which does not exist for arm64. Use:

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python \
  "torch==2.2.2" "torchvision==0.17.2" "numpy==1.26.4" "pillow==9.5.0" \
  opencv-python scipy shapely timm h5py fire pandas ftfy regex tqdm gdown \
  matplotlib scikit-learn supervision pyyaml "open_clip_torch==1.3.0" cython wandb
uv pip install --python .venv/bin/python --no-build-isolation \
  "git+https://github.com/facebookresearch/segment-anything.git" \
  "git+https://github.com/facebookresearch/detectron2.git"
uv pip install --python .venv/bin/python --no-build-isolation -e GroundingDINO
uv pip install --python .venv/bin/python "transformers==4.38.2" "tokenizers<0.19"
```

Notes:
- `transformers` must be 4.x. GroundingDINO's BERT usage breaks on 5.x.
- `pillow` must be <10 for detectron2 (`Image.LINEAR`).
- GroundingDINO's CUDA op will not build; it falls back to
  `multi_scale_deformable_attn_pytorch`, guarded by
  `torch.cuda.is_available() and value.is_cuda`. The warning is expected.

## 3. Patch segment-anything for MPS

MPS has no float64, so `SamAutomaticMaskGenerator` crashes. This lives in
site-packages and is therefore not in the patch file:

```bash
SA=.venv/lib/python3.11/site-packages/segment_anything
perl -pi -e 's/in_points = torch\.as_tensor\(transformed_points, device=self\.predictor\.device\)/in_points = torch.as_tensor(transformed_points, dtype=torch.float32, device=self.predictor.device)/' $SA/automatic_mask_generator.py
```

## 4. Weights

```bash
mkdir -p weights GroundingDINO/weights OVSeg/weights output/temp
curl -L -o weights/sam_vit_h_4b8939.pth \
  https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth
curl -L -o GroundingDINO/weights/groundingdino_swint_ogc.pth \
  https://huggingface.co/ShilongLiu/GroundingDINO/resolve/main/groundingdino_swint_ogc.pth
.venv/bin/gdown 1cn-ohxgXDrDfkzC1QdO-fi8IjbjXmgKy \
  -O OVSeg/weights/ovseg_swinbase_vitL14_ft_mpt.pth
```

**`ckpt_download.sh` is wrong.** Its Google Drive link returns the full 2.0 GB
OVSeg model, not the `ovseg_clip_l_9a1909.pth` CLIP checkpoint that
`SAMVisualizationDemo` loads. Extract it:

```bash
.venv/bin/python - <<'PY'
import torch
sd = torch.load("OVSeg/weights/ovseg_swinbase_vitL14_ft_mpt.pth", map_location="cpu")["model"]
pre = "clip_adapter.clip_model."
clip_sd = {k[len(pre):]: v for k, v in sd.items() if k.startswith(pre)}
clip_sd.pop("visual.mask_embedding", None)   # OVSeg mask-prompt extra; stock open_clip has no such param
torch.save(clip_sd, "OVSeg/weights/ovseg_clip_l_9a1909.pth")
print(len(clip_sd), "tensors")   # expect 446, ~1.71 GB
PY
```

The resulting file should be ~1710 MB, which matches the published checkpoint size.

## 5. Run

```bash
export PYTORCH_ENABLE_MPS_FALLBACK=1 PYTHONPATH=.
mkdir -p data/squash/test/images
.venv/bin/python -c "import cv2; cv2.imwrite('data/squash/test/images/plants.png', cv2.resize(cv2.imread('../plants.jpeg'), (768,1024), interpolation=cv2.INTER_AREA))"

.venv/bin/python leaf_mask_collection.py --dataset squash --mode test --dataset_dir data/squash/test/images --strip "*.png"
.venv/bin/python leaf_segmentation.py    --dataset squash --mode test
.venv/bin/python plant_segmentation.py   --dataset squash --mode test --dataset_dir data/squash/test/images --strip ".png"
.venv/bin/python viz_final.py
```

Expected on `plants.jpeg` at `eps=100`: 167 masks -> 127 leaf instances ->
5 plant instances, squash in 3 fragments, clover separated. See `../RESULTS.md`.
Runtime ~8 min on an M1 Max.
