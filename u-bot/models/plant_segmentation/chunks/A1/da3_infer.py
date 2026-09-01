"""
A1 — run Depth Anything 3 locally and keep the float output.

Produces, per (model, process_res) run, under chunks/A1/depth/<tag>/:
  depth.npy        float32 (H, W)   raw model depth, z along the optical axis
  conf.npy         float32 (H, W)   model depth confidence (if emitted)
  rgb.png          uint8            the exact pixels the model saw
  provenance.json  everything needed to reproduce and to audit the geometry

Nothing in here rescales, normalises or clips the depth. The whole point of the
chunk is that the float values survive untouched.

Usage:
    .venv/bin/python da3_infer.py --model da3-large --res 504
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "da3-src" / "src"
sys.path.insert(0, str(SRC))

# The DA3 package pulls a handful of heavy optional deps at import time, none of
# which are on the code path for single-image depth inference, and several of
# which have no arm64 macOS wheel (gsplat, pycolmap). Stub them so the import
# succeeds; if any were ever actually touched we would get an AttributeError,
# not a silently wrong number.
_STUBS = [
    "pycolmap",
    "gsplat",
    "moviepy",
    "moviepy.editor",
    "e3nn",
    "xformers",
    "xformers.ops",
    "open3d",
]
for _name in _STUBS:
    if _name not in sys.modules:
        sys.modules[_name] = types.ModuleType(_name)

import numpy as np  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402

from depth_anything_3.api import DepthAnything3  # noqa: E402

REPO = {
    "da3-large": "depth-anything/DA3-LARGE",
    "da3metric-large": "depth-anything/DA3METRIC-LARGE",
    "da3mono-large": "depth-anything/DA3MONO-LARGE",
    "da3nested-giant-large": "depth-anything/DA3NESTED-GIANT-LARGE-1.1",
}


def sha256(path: Path, limit: int | None = None) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
            if limit and f.tell() > limit:
                break
    return h.hexdigest()


def hf_revision(repo_id: str) -> str | None:
    """The exact Hub commit the weights came from.

    `PyTorchModelHubMixin` leaves `_commit_hash` unset here, so read it off the
    local cache instead — a checkpoint with no revision is not provenance.
    """
    from huggingface_hub import constants

    cache = Path(constants.HF_HUB_CACHE) / (
        "models--" + repo_id.replace("/", "--")
    )
    snaps = cache / "snapshots"
    if not snaps.is_dir():
        return None
    names = sorted(p.name for p in snaps.iterdir() if p.is_dir())
    return names[0] if len(names) == 1 else ",".join(names)


def fov_from_K(K: np.ndarray, h: int, w: int) -> dict:
    """Invert DA3's own intrinsics construction.

    `pose_encoding_to_extri_intri` builds K as
        fx = (W/2) / tan(fov_w/2),  fy = (H/2) / tan(fov_h/2),
        cx = W/2,  cy = H/2
    from a 2-vector FOV regressed by `CameraDec.fc_fov`. So the horizontal and
    vertical field of view the model assumed are recoverable exactly.
    """
    fx, fy, cx, cy = float(K[0, 0]), float(K[1, 1]), float(K[0, 2]), float(K[1, 2])
    fov_w = 2.0 * np.arctan((w / 2.0) / fx)
    fov_h = 2.0 * np.arctan((h / 2.0) / fy)
    diag = float(np.hypot(w, h))
    fov_d = 2.0 * np.arctan((diag / 2.0) / ((fx + fy) / 2.0))
    return {
        "fx_px": fx,
        "fy_px": fy,
        "cx_px": cx,
        "cy_px": cy,
        "fov_horizontal_deg": float(np.degrees(fov_w)),
        "fov_vertical_deg": float(np.degrees(fov_h)),
        "fov_diagonal_deg": float(np.degrees(fov_d)),
        # 35 mm-equivalent focal length implied by the diagonal FOV, for
        # comparison with the A1b assumption of a 26 mm-equivalent phone camera.
        # 43.266615 mm is the diagonal of a 36x24 mm frame — a definition, not
        # a fitted constant. Presentational only; nothing downstream uses it.
        "implied_35mm_equiv_mm": float(43.266615 / (2.0 * np.tan(fov_d / 2.0))),
        # f expressed at full 3000x4000 resolution, the units A1b works in.
        "principal_point_is_image_centre": abs(cx - w / 2.0) < 1e-3
        and abs(cy - h / 2.0) < 1e-3,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="da3-large", choices=sorted(REPO))
    ap.add_argument("--res", type=int, default=504, help="process_res, longest side")
    ap.add_argument("--image", default=str(HERE.parent.parent / "plants.jpeg"))
    ap.add_argument("--device", default="mps")
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()

    image = Path(args.image).resolve()
    tag = f"{args.model}_res{args.res}"
    out = Path(args.outdir) if args.outdir else HERE / "depth" / tag
    out.mkdir(parents=True, exist_ok=True)

    repo_id = REPO[args.model]
    t0 = time.time()
    model = DepthAnything3.from_pretrained(repo_id)
    device = torch.device(args.device)
    model = model.to(device=device)
    model.device = device
    t_load = time.time() - t0

    t0 = time.time()
    pred = model.inference(
        [str(image)],
        process_res=args.res,
        process_res_method="upper_bound_resize",
        export_dir=None,
    )
    t_infer = time.time() - t0

    depth = np.asarray(pred.depth[0], dtype=np.float32)
    h, w = depth.shape
    np.save(out / "depth.npy", depth)

    conf = None
    if pred.conf is not None:
        conf = np.asarray(pred.conf[0], dtype=np.float32)
        np.save(out / "conf.npy", conf)

    Image.fromarray(pred.processed_images[0]).save(out / "rgb.png")

    intr = None
    if pred.intrinsics is not None:
        K = np.asarray(pred.intrinsics[0], dtype=np.float64)
        np.save(out / "intrinsics.npy", K)
        intr = {"K": K.tolist(), **fov_from_K(K, h, w)}
        # Same camera expressed at the original 3000x4000 sampling, which is
        # what A1b's `f` sweep is denominated in.
        with Image.open(image) as im:
            ow, oh = im.size
        intr["f_at_original_resolution_px"] = {
            "fx": intr["fx_px"] * ow / w,
            "fy": intr["fy_px"] * oh / h,
            "orig_w": ow,
            "orig_h": oh,
        }

    ext = None
    if pred.extrinsics is not None:
        E = np.asarray(pred.extrinsics[0], dtype=np.float64)
        np.save(out / "extrinsics.npy", E)
        ext = E.tolist()

    finite = np.isfinite(depth)
    prov = {
        "chunk": "A1",
        "purpose": "raw float monocular depth for plants.jpeg",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_image": {
            "path": str(image),
            "sha256": sha256(image),
            "size_wh": list(Image.open(image).size),
            "exif": "stripped — no intrinsics available (see roadmap Known gaps)",
        },
        "model": {
            "family": "Depth Anything 3 (DA3)",
            "hf_repo": repo_id,
            "hf_revision": getattr(model, "_commit_hash", None) or hf_revision(repo_id),
            "preset": model.model_name,
            "config": model.config if isinstance(model.config, dict) else str(model.config),
            "code": {
                "repo": "https://github.com/ByteDance-Seed/depth-anything-3",
                "commit": subprocess.run(
                    ["git", "-C", str(HERE / "da3-src"), "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                "import_stubs": _STUBS,
            },
        },
        "output_semantics": {
            "quantity": "depth",
            "is_disparity": False,
            "convention": "z-distance along the optical axis, NOT ray length",
            "evidence": (
                "depth_anything_3.utils.geometry.pixel_space_to_camera_space does "
                "K^-1 @ [u, v, 1] * depth, i.e. the ray is normalised to z=1 before "
                "scaling, which is the pinhole z-depth convention. Pixel centres are "
                "integer indices 0..W-1 (torch.meshgrid over arange), no +0.5 offset."
            ),
            "is_metric": int(getattr(pred, "is_metric", 0) or 0),
            "metric_scale_factor": pred.scale_factor,
            "units": (
                "metres (model's claim; unverifiable for this image — no fiducial)"
                if getattr(pred, "is_metric", 0)
                else "relative / up to unknown scale"
            ),
        },
        "preprocessing": {
            "process_res": args.res,
            "process_res_method": "upper_bound_resize",
            "note": (
                "longest side resized to process_res, then each side rounded to the "
                "nearest multiple of the ViT patch size 14; ImageNet normalisation"
            ),
            "patch_size": 14,
            "model_input_hw": [h, w],
        },
        "camera": {
            "predicted_by_model": intr is not None,
            "source": (
                "DA3 CameraDec head: fc_fov regresses (fov_h, fov_w) in radians; "
                "pose_encoding_to_extri_intri turns them into K with the principal "
                "point pinned to the image centre and zero skew"
                if intr is not None
                else "this preset has no cam_dec — no intrinsics are predicted, and "
                "none were supplied"
            ),
            "intrinsics": intr,
            "extrinsics_c2w_or_w2c": "w2c (3x4), identity-ish for a single view",
            "extrinsics": ext,
        },
        "runtime": {
            "device": str(device),
            "torch": torch.__version__,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "autocast_dtype": "float16 (torch.cuda.is_bf16_supported() is False off-CUDA)",
            "load_seconds": round(t_load, 2),
            "inference_seconds": round(t_infer, 2),
        },
        "depth_stats": {
            "shape": [h, w],
            "dtype": "float32",
            "min": float(depth[finite].min()),
            "max": float(depth[finite].max()),
            "mean": float(depth[finite].mean()),
            "median": float(np.median(depth[finite])),
            "p01": float(np.percentile(depth[finite], 1)),
            "p99": float(np.percentile(depth[finite], 99)),
            "n_nonfinite": int((~finite).sum()),
            "n_distinct_values": int(np.unique(depth[finite]).size),
        },
        "conf_stats": None
        if conf is None
        else {
            "min": float(conf.min()),
            "max": float(conf.max()),
            "median": float(np.median(conf)),
        },
        "caveats": [
            "No EXIF, no calibration, no fiducial. Absolute scale is unresolved.",
            "Any intrinsics above are the MODEL's estimate, not a measurement. "
            "Using them makes the reconstruction self-consistent with the depth, "
            "not correct.",
            "Depth is emitted at the model's internal resolution, not 3000x4000. "
            "Upsampling it does not create detail.",
        ],
    }
    with open(out / "provenance.json", "w") as f:
        json.dump(prov, f, indent=2)

    print(f"[{tag}] depth {depth.shape} "
          f"range [{prov['depth_stats']['min']:.4f}, {prov['depth_stats']['max']:.4f}] "
          f"metric={prov['output_semantics']['is_metric']} "
          f"distinct={prov['depth_stats']['n_distinct_values']} "
          f"infer={t_infer:.1f}s")
    if intr is not None:
        print(f"    FOV h={intr['fov_horizontal_deg']:.2f} deg "
              f"v={intr['fov_vertical_deg']:.2f} deg "
              f"-> {intr['implied_35mm_equiv_mm']:.1f} mm equiv, "
              f"f@3000x4000 = {intr['f_at_original_resolution_px']['fx']:.0f} px")
    print(f"    -> {out}")


if __name__ == "__main__":
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    main()
