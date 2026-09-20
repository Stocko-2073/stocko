"""
A1 — the FOV Depth Anything 3 assumed, and how much to trust it.

The roadmap calls this "the largest unquantified error in the whole stack".
It is quantifiable, and this script quantifies it.

Where the number comes from
---------------------------
DA3's any-view presets carry a `CameraDec` head whose `fc_fov` branch regresses
a 2-vector (fov_h, fov_w) in radians. `pose_encoding_to_extri_intri` turns that
into K with

    fy = (H/2) / tan(fov_h/2)     fx = (W/2) / tan(fov_w/2)
    cx = W/2                      cy = H/2      skew = 0

So the model's internal camera is fully recoverable, and its principal point is
pinned to the image centre by construction — the same assumption A1b registers
as a category (d) constant, except DA3 made it first and silently.

The metric presets (`da3metric-*`, `da3mono-*`) have **no** cam_dec and predict
no camera at all.

Why it matters twice over
-------------------------
1. Shape. f sets how much perspective is in the reconstruction.
2. Scale. `utils.alignment.apply_metric_scaling` computes metric depth as
   `depth * (f / 300)` — DA3's absolute metric claim is *directly proportional*
   to its own guessed focal length. Any error in the FOV estimate passes
   straight through into metres.

Run: .venv/bin/python camera_report.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# A physically realisable camera with square pixels has fx == fy. Anything
# further out than this is the head extrapolating, not estimating.
# (a) instrument: it is a property of the model, checked not chosen.
PIXEL_ASPECT_TOLERANCE = 0.05


def collect() -> list[dict]:
    rows = []
    for prov_path in sorted((HERE / "depth").glob("*/provenance.json")):
        p = json.loads(prov_path.read_text())
        cam = p["camera"]["intrinsics"]
        run = prov_path.parent.name
        row = {
            "run": run,
            "model": p["model"]["hf_repo"],
            "process_res": p["preprocessing"]["process_res"],
            "input_hw": p["preprocessing"]["model_input_hw"],
            "predicts_camera": cam is not None,
            "is_metric": p["output_semantics"]["is_metric"],
            "metric_scale_factor": p["output_semantics"]["metric_scale_factor"],
        }
        if cam:
            aspect = cam["fx_px"] / cam["fy_px"]
            row.update(
                {
                    "fx": cam["fx_px"],
                    "fy": cam["fy_px"],
                    "fov_h_deg": cam["fov_horizontal_deg"],
                    "fov_v_deg": cam["fov_vertical_deg"],
                    "pixel_aspect_fx_over_fy": aspect,
                    "physically_consistent": bool(
                        abs(aspect - 1.0) <= PIXEL_ASPECT_TOLERANCE
                    ),
                    "f_at_3000x4000_from_fx": cam["f_at_original_resolution_px"]["fx"],
                    "f_at_3000x4000_from_fy": cam["f_at_original_resolution_px"]["fy"],
                    "implied_35mm_equiv_mm": cam["implied_35mm_equiv_mm"],
                    "principal_point_at_centre": cam["principal_point_is_image_centre"],
                }
            )
        rows.append(row)
    return rows


def determinism_check(run_dir: Path, n: int = 2) -> dict:
    """Re-run the model and diff, so the noise floor measured elsewhere can be
    called instrument resolution rather than sampling jitter."""
    import tempfile

    prov = json.loads((run_dir / "provenance.json").read_text())
    model_key = {
        "depth-anything/DA3-LARGE": "da3-large",
        "depth-anything/DA3METRIC-LARGE": "da3metric-large",
        "depth-anything/DA3MONO-LARGE": "da3mono-large",
        "depth-anything/DA3NESTED-GIANT-LARGE-1.1": "da3nested-giant-large",
    }[prov["model"]["hf_repo"]]
    res = prov["preprocessing"]["process_res"]
    base = np.load(run_dir / "depth.npy").astype(np.float64)
    diffs = []
    for _ in range(n - 1):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(
                [
                    str(HERE / ".venv/bin/python"), str(HERE / "da3_infer.py"),
                    "--model", model_key, "--res", str(res), "--outdir", td,
                ],
                check=True, capture_output=True,
                env={"PATH": "/usr/bin:/bin", "PYTORCH_ENABLE_MPS_FALLBACK": "1",
                     "HOME": str(Path.home())},
            )
            other = np.load(Path(td) / "depth.npy").astype(np.float64)
        d = np.abs(other - base)
        diffs.append(
            {
                "max_abs_diff": float(d.max()),
                "rms_diff": float(np.sqrt((d**2).mean())),
                "identical": bool(d.max() == 0.0),
            }
        )
    med = float(np.median(base))
    return {
        "run": run_dir.name,
        "repeats": n,
        "median_depth": med,
        "diffs": diffs,
        "rms_diff_rdu": diffs[0]["rms_diff"] / med if diffs else None,
    }


def main() -> None:
    rows = collect()
    out = {
        "how_the_fov_is_obtained": {
            "head": "depth_anything_3.model.cam_dec.CameraDec.fc_fov",
            "output": "(fov_h, fov_w) in radians, ReLU-activated",
            "to_K": "fy=(H/2)/tan(fov_h/2), fx=(W/2)/tan(fov_w/2), cx=W/2, cy=H/2, skew=0",
            "principal_point": "pinned to the image centre by construction",
            "distortion": "none modelled",
            "presets_without_a_camera_head": ["da3metric-*", "da3mono-*"],
            "metric_scale_dependence": (
                "utils.alignment.apply_metric_scaling: metric_depth = depth * f/300. "
                "DA3's absolute scale is directly proportional to its own guessed f."
            ),
        },
        "pixel_aspect_tolerance": PIXEL_ASPECT_TOLERANCE,
        "runs": rows,
    }

    cam_rows = [r for r in rows if r["predicts_camera"]]
    fam = {}
    for r in cam_rows:
        fam.setdefault(r["model"], []).append(r)

    print(
        f"{'run':30s} {'res':>5} {'fx':>8} {'fy':>8} {'hFOV':>7} {'vFOV':>7} "
        f"{'fx/fy':>6} {'f@3000':>7} {'mm-eq':>6}  consistent"
    )
    for r in sorted(cam_rows, key=lambda x: (x["model"], x["process_res"])):
        print(
            f"{r['run']:30s} {r['process_res']:5d} {r['fx']:8.1f} {r['fy']:8.1f} "
            f"{r['fov_h_deg']:7.2f} {r['fov_v_deg']:7.2f} "
            f"{r['pixel_aspect_fx_over_fy']:6.3f} "
            f"{r['f_at_3000x4000_from_fx']:7.0f} {r['implied_35mm_equiv_mm']:6.1f}  "
            f"{'yes' if r['physically_consistent'] else 'NO'}"
        )

    good = [r for r in cam_rows if r["physically_consistent"]]
    if good:
        fs = np.array([r["f_at_3000x4000_from_fx"] for r in good])
        out["fov_stability"] = {
            "n_runs_with_a_camera": len(cam_rows),
            "n_physically_consistent": len(good),
            "consistent_runs": [r["run"] for r in good],
            "f_at_3000x4000_px": {
                "min": float(fs.min()),
                "max": float(fs.max()),
                "mean": float(fs.mean()),
                "spread_over_mean": float((fs.max() - fs.min()) / fs.mean()),
            },
            "all_runs_f_at_3000x4000_px": {
                r["run"]: r["f_at_3000x4000_from_fx"] for r in cam_rows
            },
            "comparison_to_A1b_assumption": {
                "A1b_f_initial_px": 3005,
                "ratio_mean_over_A1b": float(fs.mean() / 3005),
                "reading": (
                    "DA3 thinks the lens is longer than a 26 mm-equivalent phone "
                    "main camera. If DA3's estimate is right, A1b's default f is "
                    "too short; if A1b is right, DA3's depth carries the "
                    "corresponding perspective error. Nothing in this image can "
                    "settle which."
                ),
            },
        }
        print(
            f"\nphysically-consistent runs only: f@3000x4000 in "
            f"[{fs.min():.0f}, {fs.max():.0f}] px, mean {fs.mean():.0f} px "
            f"({fs.mean() / 3005:.2f}x A1b's assumed 3005 px)"
        )

    # ---- determinism -------------------------------------------------------
    try:
        out["determinism"] = determinism_check(HERE / "depth" / "da3-large_res504")
        d = out["determinism"]["diffs"][0]
        print(
            f"\ndeterminism (da3-large_res504, 2 runs): "
            f"identical={d['identical']} max|diff|={d['max_abs_diff']:.3e} "
            f"rms={out['determinism']['rms_diff_rdu']:.3e} rdu"
        )
    except Exception as exc:  # pragma: no cover
        out["determinism"] = {"error": repr(exc)}
        print(f"\ndeterminism check failed: {exc!r}")

    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "camera.json").write_text(json.dumps(out, indent=2))

    # ---- figure ------------------------------------------------------------
    if len(cam_rows) > 1:
        fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
        for model, rs in fam.items():
            rs = sorted(rs, key=lambda r: r["process_res"])
            x = [r["process_res"] for r in rs]
            ax[0].plot(x, [r["fov_h_deg"] for r in rs], "o-", label=f"{model} hFOV")
            ax[0].plot(x, [r["fov_v_deg"] for r in rs], "s--", label=f"{model} vFOV")
            ax[1].plot(x, [r["pixel_aspect_fx_over_fy"] for r in rs], "o-", label=model)
        ax[0].set_xlabel("process_res (longest side, px)")
        ax[0].set_ylabel("field of view (deg)")
        ax[0].set_title("DA3's internally estimated FOV\nfor one fixed image")
        ax[0].legend(fontsize=7)
        ax[0].grid(alpha=0.3)
        ax[1].axhline(1.0, color="k", lw=0.8)
        ax[1].axhspan(
            1 - PIXEL_ASPECT_TOLERANCE, 1 + PIXEL_ASPECT_TOLERANCE,
            color="green", alpha=0.12,
        )
        ax[1].set_xlabel("process_res (longest side, px)")
        ax[1].set_ylabel("fx / fy")
        ax[1].set_title(
            "pixel aspect ratio\n(square pixels => 1; shaded band = plausible)"
        )
        ax[1].legend(fontsize=7)
        ax[1].grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(HERE / "results" / "fig_fov_vs_resolution.png", dpi=110)
        plt.close(fig)

    print(f"\n-> {HERE / 'results' / 'camera.json'}")


if __name__ == "__main__":
    main()
