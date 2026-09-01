"""
A1 — what did the 8-bit preview actually cost?

`plants_depth.webp` is 1008x1344, both sides exact multiples of 14, which is
what DA3's InputProcessor produces from a 3000x4000 image at process_res=1344.
So the preview and our float run at res 1344 sit on the *same pixel grid* and
can be compared pixel for pixel with no resampling.

Three questions, in order:

1. **What is the preview a preview of?** Fit it against each DA3 variant, both
   as an affine function of depth and as an affine function of disparity, and
   report which mapping and which model it matches. This is forensics on an
   asset we inherited without provenance.

2. **What does 8-bit cost, isolated?** Take our own float depth, push it through
   the same normalise-to-255-levels round trip, and re-fit the soil surface.
   Same model, same pixels, only the container changes.

3. **What does the real preview file cost?** Same fit on the actual webp, which
   adds lossy chroma compression and whatever normalisation was used, on top of
   the quantisation.

Run: .venv/bin/python compare_preview.py
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from depth_to_cloud import depth_to_cloud, load_depth_product  # noqa: E402
from measure_quantisation import (  # noqa: E402
    immerkaer_sigma,
    local_plane_residuals,
    noise_floor,
    representation_step,
    soil_fit_report,
)

PRIMARY = "da3nested-giant-large_res1344"
PREVIEW = ROOT / "plants_depth.webp"
LEVELS = 256  # an 8-bit container. Not a tunable — it is what the file is.


def affine_r2(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """Least-squares y ~ a x + b; returns (a, b, R^2)."""
    A = np.stack([x, np.ones_like(x)], 1)
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    pred = A @ coef
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return float(coef[0]), float(coef[1]), 1.0 - ss_res / ss_tot


def _rank(v: np.ndarray) -> np.ndarray:
    order = np.argsort(v, kind="stable")
    r = np.empty_like(order, dtype=np.float64)
    r[order] = np.arange(v.size, dtype=np.float64)
    return r


def quantise_8bit(depth: np.ndarray, in_disparity: bool) -> np.ndarray:
    """Normalise to [0, 255], round, and map straight back — exactly what an
    8-bit preview does to a float depth map."""
    v = 1.0 / depth if in_disparity else depth
    lo, hi = float(np.nanmin(v)), float(np.nanmax(v))
    q = np.round((v - lo) / (hi - lo) * (LEVELS - 1))
    back = q / (LEVELS - 1) * (hi - lo) + lo
    return 1.0 / back if in_disparity else back


def webp_roundtrip(depth: np.ndarray, in_disparity: bool, quality: int = 90) -> np.ndarray:
    """The preview's full pipeline: 8-bit normalise, then lossy WebP."""
    v = 1.0 / depth if in_disparity else depth
    lo, hi = float(np.nanmin(v)), float(np.nanmax(v))
    img = np.round((v - lo) / (hi - lo) * 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(img).convert("RGB").save(buf, format="WEBP", quality=quality)
    buf.seek(0)
    back8 = np.asarray(Image.open(buf).convert("L"), dtype=np.float64)
    back = back8 / 255.0 * (hi - lo) + lo
    return 1.0 / back if in_disparity else back


def structure_lost(z: np.ndarray) -> dict:
    """How much local relief the container can no longer express.

    A4 groups plant material by depth *continuity* between adjacent pixels. If
    neighbouring pixels are forced onto the same quantisation level, the
    difference A4 needs to read is gone — and unlike noise, it cannot be
    averaged back. Three views of the same loss:

    * fraction of 4-neighbour pairs with *exactly* equal depth;
    * fraction of 9x9 windows containing a single depth level (dead regions);
    * median number of distinct levels inside a 9x9 window.
    """
    from numpy.lib.stride_tricks import sliding_window_view

    fin = np.isfinite(z)
    dh = z[:, 1:] - z[:, :-1]
    dv = z[1:, :] - z[:-1, :]
    mh = fin[:, 1:] & fin[:, :-1]
    mv = fin[1:, :] & fin[:-1, :]
    diffs = np.concatenate([dh[mh], dv[mv]])
    zeros = float((diffs == 0).mean())

    v = sliding_window_view(np.where(fin, z, np.nan), (9, 9))[::9, ::9]
    v = v.reshape(v.shape[0], v.shape[1], -1)
    counts = np.array(
        [
            len(np.unique(w[np.isfinite(w)]))
            for row in v
            for w in row
        ]
    )
    return {
        "fraction_neighbour_pairs_identical": zeros,
        "fraction_windows_single_level": float((counts <= 1).mean()),
        "fraction_windows_two_or_fewer_levels": float((counts <= 2).mean()),
        "median_levels_per_9x9_window": float(np.median(counts)),
        "n_windows": int(counts.size),
    }


def main() -> None:
    out: dict = {}

    prod = load_depth_product(HERE / "depth" / PRIMARY)
    float_depth = prod.depth.astype(np.float64)
    H, W = float_depth.shape

    prev_img = Image.open(PREVIEW)
    prev_rgb = np.asarray(prev_img.convert("RGB"))
    prev = np.asarray(prev_img.convert("L"), dtype=np.float64)
    out["preview_file"] = {
        "path": str(PREVIEW),
        "size_wh": list(prev_img.size),
        "format": prev_img.format,
        "mode": prev_img.mode,
        "n_distinct_levels": int(np.unique(prev).size),
        "channels_identical": bool(
            np.array_equal(prev_rgb[..., 0], prev_rgb[..., 1])
            and np.array_equal(prev_rgb[..., 1], prev_rgb[..., 2])
        ),
        "grid_matches_float_run": [H, W] == list(prev.shape),
        "note": (
            "1008x1344, both multiples of the ViT patch size 14 — consistent with "
            "DA3 at process_res=1344 on a 3000x4000 input, i.e. the same grid as "
            "our primary float run"
        ),
    }
    print(f"preview {prev.shape} levels={out['preview_file']['n_distinct_levels']} "
          f"grid_match={out['preview_file']['grid_matches_float_run']}")
    if prev.shape != float_depth.shape:
        raise SystemExit("preview grid does not match the float run; aborting")

    # ---- 1. forensics: what is the preview a preview of? -------------------
    # brighter = nearer, so the preview is a decreasing function of depth.
    fits = {}
    for run in sorted(p.name for p in (HERE / "depth").iterdir() if (p / "depth.npy").exists()):
        d = np.load(HERE / "depth" / run / "depth.npy").astype(np.float64)
        if d.shape != prev.shape:
            continue
        m = np.isfinite(d) & (d > 0)
        # Spearman rho is invariant to ANY monotone renormalisation, so it
        # answers "is this the same depth field?" without assuming the preview
        # was normalised linearly. Computed on a fixed subsample for speed.
        idx = np.flatnonzero(m.ravel())[::17]
        rho = float(
            np.corrcoef(
                _rank(prev.ravel()[idx]), _rank(d.ravel()[idx])
            )[0, 1]
        )
        for space, x in (("depth", d[m]), ("disparity", 1.0 / d[m])):
            a, b, r2 = affine_r2(prev[m], x)
            resid_rms = float(
                np.sqrt((((a * prev[m] + b) - x) ** 2).mean()) / np.median(d[m])
            )
            fits[f"{run} | {space}"] = {
                "gain": a, "offset": b, "r2": r2,
                "affine_residual_rms_rdu": resid_rms,
                "spearman_rho_vs_preview": rho,
            }
    out["preview_identification"] = dict(
        sorted(fits.items(), key=lambda kv: -kv[1]["r2"])
    )
    print("\npreview vs float, best affine fits (higher R^2 = better match):")
    for k, v in list(out["preview_identification"].items())[:6]:
        print(f"  R^2={v['r2']:.5f}  rho={v['spearman_rho_vs_preview']:.5f}  "
              f"affine_resid={v['affine_residual_rms_rdu']:.4f} rdu  {k}")

    best_key = max(fits, key=lambda k: fits[k]["r2"])
    preview_space = best_key.split("|")[1].strip()
    out["preview_normalisation_space"] = preview_space

    # ---- 2 & 3. the cost of the container ---------------------------------
    # Reconstruct a float depth from the preview using the best mapping, so the
    # preview can be fitted in the same units as the float depth.
    a, b = fits[best_key]["gain"], fits[best_key]["offset"]
    prev_as = a * prev + b
    prev_depth = 1.0 / prev_as if preview_space == "disparity" else prev_as
    prev_depth = np.where(np.isfinite(prev_depth) & (prev_depth > 0), prev_depth, np.nan)

    variants = {
        "float (as produced)": float_depth,
        f"float -> 8 bit in {preview_space}": quantise_8bit(float_depth, preview_space == "disparity"),
        f"float -> 8 bit + lossy webp in {preview_space}": webp_roundtrip(
            float_depth, preview_space == "disparity"
        ),
        "the actual plants_depth.webp": prev_depth,
    }

    K = prod.model_intrinsics
    assert K is not None
    sigma_ref = None
    rows = {}
    for name, d in variants.items():
        m = np.isfinite(d) & (d > 0)
        dd = np.where(m, d, np.nan)
        cloud = depth_to_cloud(
            np.nan_to_num(dd, nan=-1.0), _fixed_camera(K), mode="scale_free"
        )
        ras = cloud.as_raster((H, W))
        z = ras[..., 2]
        rep = representation_step(np.where(np.isfinite(z), z, np.nan))
        sig = immerkaer_sigma(z)
        nf = noise_floor(local_plane_residuals(ras, win=9, stride=4))
        if sigma_ref is None:
            sigma_ref = nf["p10"]
        sub = depth_to_cloud(
            np.nan_to_num(dd, nan=-1.0), _fixed_camera(K), mode="scale_free", subsample=3
        )
        soil = {
            f"thr_{t}": soil_fit_report(sub.xyz, t, f"{name}@{t}")
            for t in (0.006, 0.012, 0.035)
        }
        rows[name] = {
            "representation": rep,
            "immerkaer_sigma_rdu": sig,
            "noise_floor_p10_rdu": nf["p10"],
            "noise_floor_p50_rdu": nf["p50"],
            "noise_floor_caveat": (
                "for a quantised container this statistic collapses toward zero: "
                "the flattest windows are staircase treads, perfectly flat by "
                "construction. Read structure_lost instead."
            ),
            "structure_lost": structure_lost(z),
            "soil_fit": soil,
            "quantisation_step_rdu": rep["median_gap"],
        }
        sl = rows[name]["structure_lost"]
        print(
            f"\n{name}\n"
            f"  distinct levels     {rep['n_distinct_values']:>9d}  "
            f"({rep['effective_bits']:.1f} bits)\n"
            f"  median step         {rep['median_gap']:.3e} rdu\n"
            f"  hi-freq sigma       {sig:.3e} rdu\n"
            f"  local plane p10     {nf['p10']:.3e} rdu\n"
            f"  flat 4-neighbours   {sl['fraction_neighbour_pairs_identical']:.4f}\n"
            f"  dead 9x9 windows    {sl['fraction_windows_single_level']:.4f}\n"
            f"  median levels/9x9   {sl['median_levels_per_9x9_window']:.1f}\n"
            f"  soil rms @0.012     {soil['thr_0.012']['inlier_residual_rms_rdu']:.5f} rdu "
            f"(inliers {soil['thr_0.012']['inlier_fraction']:.3f})"
        )
    out["cost_of_the_container"] = rows

    # ---- headline ratios ---------------------------------------------------
    f = rows["float (as produced)"]
    q = rows[f"float -> 8 bit in {preview_space}"]
    p = rows["the actual plants_depth.webp"]
    out["headline"] = {
        "float_noise_floor_rdu": f["noise_floor_p10_rdu"],
        "eight_bit_step_rdu": q["quantisation_step_rdu"],
        "step_over_float_noise_floor": q["quantisation_step_rdu"] / f["noise_floor_p10_rdu"],
        "float_effective_bits": f["representation"]["effective_bits"],
        "preview_effective_bits": p["representation"]["effective_bits"],
        "soil_rms_float_rdu": f["soil_fit"]["thr_0.012"]["inlier_residual_rms_rdu"],
        "soil_rms_8bit_rdu": q["soil_fit"]["thr_0.012"]["inlier_residual_rms_rdu"],
        "soil_rms_actual_preview_rdu": p["soil_fit"]["thr_0.012"]["inlier_residual_rms_rdu"],
        "soil_rms_penalty_from_8bit": q["soil_fit"]["thr_0.012"][
            "inlier_residual_rms_rdu"
        ]
        / f["soil_fit"]["thr_0.012"]["inlier_residual_rms_rdu"]
        - 1.0,
        "neighbour_pairs_flattened_float": f["structure_lost"][
            "fraction_neighbour_pairs_identical"
        ],
        "neighbour_pairs_flattened_preview": p["structure_lost"][
            "fraction_neighbour_pairs_identical"
        ],
        "median_levels_per_9x9_float": f["structure_lost"][
            "median_levels_per_9x9_window"
        ],
        "median_levels_per_9x9_preview": p["structure_lost"][
            "median_levels_per_9x9_window"
        ],
    }
    print("\nHEADLINE")
    for k, v in out["headline"].items():
        print(f"  {k:>42s}: {v:.5g}")

    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "preview_vs_float.json").write_text(json.dumps(out, indent=2))

    _figures(float_depth, prev, prev_depth, variants, rows, preview_space)


def _fixed_camera(K):
    """The comparison holds the camera fixed on purpose — only the depth
    container changes — so every variant is back-projected through the same
    model-estimated K, tagged as such."""
    from depth_to_cloud import Intrinsics

    return Intrinsics(
        fx=K.fx, fy=K.fy, cx=K.cx, cy=K.cy, width=K.width, height=K.height,
        provenance="model_estimated",
        note="held fixed across the float/preview comparison",
    )


def _figures(float_depth, prev, prev_depth, variants, rows, space):
    fig, ax = plt.subplots(1, 4, figsize=(16, 6))
    ax[0].imshow(float_depth, cmap="turbo")
    ax[0].set_title(f"float depth\n{np.unique(float_depth).size} distinct values")
    ax[1].imshow(prev_depth, cmap="turbo")
    ax[1].set_title(
        f"the 8-bit preview, mapped back to depth\n{np.unique(prev).size} levels"
    )
    # NB this difference is NOT the quantisation cost: it also contains the
    # difference between two separate inference runs. The isolated quantisation
    # cost is the "float -> 8 bit" row in the table.
    diff = prev_depth - float_depth
    m = np.isfinite(diff)
    lim = float(np.nanpercentile(np.abs(diff[m]), 99))
    im = ax[2].imshow(diff, cmap="coolwarm", vmin=-lim, vmax=lim)
    ax[2].set_title("preview - float (depth units)")
    plt.colorbar(im, ax=ax[2], fraction=0.046)
    # a horizontal slice makes the staircase visible
    r = float_depth.shape[0] // 2
    ax[3].plot(float_depth[r], lw=0.8, label="float")
    ax[3].plot(prev_depth[r], lw=0.8, label="preview")
    ax[3].set_title(f"row {r} profile")
    ax[3].legend()
    for a in ax[:3]:
        a.axis("off")
    fig.suptitle("A1 — float depth vs the inherited 8-bit preview (same 1008x1344 grid)")
    fig.tight_layout()
    fig.savefig(HERE / "results" / "fig_preview_vs_float.png", dpi=110)
    plt.close(fig)

    # NB: the local-plane p10 statistic is NOT plotted for the quantised
    # variants — it collapses to zero there because the flattest windows are
    # staircase treads. What is plotted instead is what the container can no
    # longer express.
    fig, ax = plt.subplots(1, 3, figsize=(13, 4.4))
    names = list(rows)
    short = ["float\n(as produced)", "8 bit", "8 bit\n+ webp", "the actual\npreview file"]
    x = np.arange(len(names))

    ax[0].bar(x, [rows[n]["quantisation_step_rdu"] for n in names], color="tab:orange")
    ax[0].axhline(
        rows[names[0]]["immerkaer_sigma_rdu"], color="k", ls="--", lw=1,
        label="float depth resolution floor",
    )
    ax[0].set_yscale("log")
    ax[0].set_ylabel("rdu (1 rdu = median scene depth)")
    ax[0].set_title("representation step")
    ax[0].legend(fontsize=7)

    ax[1].bar(
        x,
        [rows[n]["structure_lost"]["fraction_neighbour_pairs_identical"] for n in names],
        color="tab:red",
    )
    ax[1].set_ylabel("fraction")
    ax[1].set_title("adjacent pixels forced to equal depth\n(what A4 reads, gone)")

    ax[2].bar(
        x,
        [rows[n]["structure_lost"]["median_levels_per_9x9_window"] for n in names],
        color="tab:blue",
    )
    ax[2].set_yscale("log")
    ax[2].set_ylabel("distinct depth levels")
    ax[2].set_title("median levels inside a 9x9 window")

    for a in ax:
        a.set_xticks(x)
        a.set_xticklabels(short, fontsize=8)
        a.grid(axis="y", alpha=0.3)
    fig.suptitle("A1 — what the 8-bit container costs")
    fig.tight_layout()
    fig.savefig(HERE / "results" / "fig_depth_resolution.png", dpi=110)
    plt.close(fig)

    # zoomed staircase: the clearest single picture of what 8 bits did
    fig, ax = plt.subplots(figsize=(9, 4))
    r = float_depth.shape[0] // 2
    sl = slice(400, 520)
    ax.plot(np.arange(sl.start, sl.stop), float_depth[r, sl], lw=1.2, label="float")
    ax.plot(
        np.arange(sl.start, sl.stop),
        variants[f"float -> 8 bit in {space}"][r, sl],
        lw=1.2,
        label=f"same depth, 8-bit in {space}",
    )
    ax.plot(np.arange(sl.start, sl.stop), prev_depth[r, sl], lw=1.0, alpha=0.8,
            label="the inherited preview")
    ax.set_xlabel("column")
    ax.set_ylabel("depth")
    ax.set_title(f"A1 — row {r}, columns {sl.start}-{sl.stop}: the 8-bit staircase")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(HERE / "results" / "fig_staircase.png", dpi=110)
    plt.close(fig)
    print(f"\n-> figures in {HERE / 'results'}")


if __name__ == "__main__":
    main()
