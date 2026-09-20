"""A7 — figures. Each one exists to be looked at, not to decorate a document.

  fig_stimulus.png    what the model was actually shown, both framings
  fig_r2_confusion.png  the R2-critical confusion per condition — small
                      multiples, because crop-mislabel *counts* and weed-reach
                      *fractions* are different quantities and must not share
                      an axis
  fig_operating.png   the R2 trade-off directly: crop put at risk against weed
                      reached, as the confidence floor sweeps, one path per
                      condition. This is the curve A8's gate is set from.
  fig_hard_context.png  the context ablation — the same hard regions with the
                      surround taken away and given back

Run:  ../A3/.venv/bin/python figs.py
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt      # noqa: E402
import numpy as np                   # noqa: E402
from PIL import Image                # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a7_data import load_components  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
FIGS = os.path.join(HERE, "figs")

# Categorical palette reused unchanged from A4's `figures.py`, so a colour means
# the same thing across the two chunks. Extended by one slot (TEAL) for the
# fourth condition and re-validated with the dataviz skill's checker on the
# light surface #fcfcfb: lightness band PASS, chroma PASS, CVD separation
# worst-adjacent dE 17.9 deutan / 14.4 tritan PASS, normal-vision dE 26.9 PASS,
# contrast PASS.
BLUE, ORANGE, PURPLE, TEAL = "#3366CC", "#E8710A", "#7A3FBF", "#12866F"
INK, MUTED, GRID = "#1b1b1b", "#5c5c5c", "#dcdcd8"
COND_COLOUR = {"A/r2": BLUE, "A/neutral": ORANGE,
               "B/r2": PURPLE, "B/neutral": TEAL}


def _tidy(ax):
    ax.set_facecolor("white")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("bottom", "left"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(True, color=GRID, lw=0.8, alpha=0.7)
    ax.set_axisbelow(True)


def scores():
    return json.load(open(os.path.join(RES, "a7_scores.json")))


# ------------------------------------------------------------------ stimulus
def fig_stimulus():
    """What the model saw. No chart — the stimulus is the evidence."""
    a = Image.open(os.path.join(HERE, "renders", "A", "region_001.png"))
    b = Image.open(os.path.join(HERE, "renders", "B", "montage_06.png"))
    fig = plt.figure(figsize=(15, 8.4))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.35], hspace=0.13)
    ax = fig.add_subplot(gs[0]); ax.imshow(a); ax.axis("off")
    ax.set_title("framing A — one call per region: whole scene, marked zoom, "
                 "and the same zoom unmarked (region 1, the crop component)",
                 color=INK, fontsize=10, loc="left")
    ax2 = fig.add_subplot(gs[1]); ax2.imshow(b); ax2.axis("off")
    ax2.set_title("framing B — one global look: 12 full-resolution tiles, every "
                  "region outlined and stamped with its ID (tile 6 of 12)",
                  color=INK, fontsize=10, loc="left")
    fig.suptitle("A7 stimuli — the VLM is given region IDs and never a "
                 "coordinate (R3)", color=MUTED, fontsize=9, y=0.985)
    fig.savefig(os.path.join(FIGS, "fig_stimulus.png"), dpi=95,
                facecolor="white", bbox_inches="tight")
    plt.close(fig)


# ----------------------------------------------------------- R2 confusion
def fig_r2_confusion():
    """Small multiples: four quantities, four axes, never one shared axis."""
    rep = scores()
    conds = [k for k in ("A/r2", "A/neutral", "B/r2", "B/neutral")
             if k in rep["conditions"]]
    panels = [
        ("crop_mislabels", "crop components called `remove`\n"
                           "(catastrophic — the number A8's gate drives to 0)",
         "count", False),
        ("crop_px_at_risk", "fraction of ground-truth CROP pixels\n"
                            "inside a component called `remove`",
         "fraction", True),
        ("weed_px_reached", "fraction of ground-truth WEED pixels\n"
                            "reached (the benefit side — higher is better)",
         "fraction", True),
        ("unsure_rate", "`unsure` rate over the 73 components asked",
         "fraction", True),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(17, 4.4))
    y = np.arange(len(conds))
    for ax, (key, title, unit, is_frac) in zip(axes, panels):
        vals, rng = [], []
        for c in conds:
            vals.append(rep["conditions"][c]["majority_vote_score"][key])
            rng.append(rep["conditions"][c]["across_repeats_minmax"][key])
        _tidy(ax)
        ax.barh(y, vals, height=0.55,
                color=[COND_COLOUR[c] for c in conds], zorder=2)
        # The min–max across repeats is drawn as its own span, not as an error
        # bar on the bar tip. With two repeats the "majority vote" is really
        # unanimous-else-`unsure`, so it can sit *outside* the range of the two
        # runs it summarises — a legitimate and interesting fact that an error
        # bar would have to hide (or crash on, which is how it was caught).
        for i, (a, b) in enumerate(rng):
            ax.hlines(i + 0.42, a, b, color=MUTED, lw=1.4, zorder=4)
            ax.vlines([a, b], i + 0.33, i + 0.51, color=MUTED, lw=1.4, zorder=4)
        ax.set_yticks(y); ax.set_yticklabels(conds, color=INK, fontsize=9)
        ax.invert_yaxis()
        ax.set_title(title, color=INK, fontsize=9, loc="left")
        for i, v in enumerate(vals):          # direct labels, selectively
            ax.text(v, i, f"  {v:.1%}" if is_frac else f"  {v:g}",
                    va="center", color=MUTED, fontsize=8.5)
        ax.set_xlim(0, max(max(vals + [b for _, b in rng]) * 1.45, 1e-9))
        if is_frac:
            # Tick precision follows the range, not a global default: the
            # crop-at-risk panel spans 0-2 % and would otherwise print six
            # ticks all reading "0%" or "1%".
            hi_v = max(vals + [b for _, b in rng])
            dp = 0 if hi_v > 0.15 else (1 if hi_v > 0.02 else 2)
            ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
                lambda v, _, d=dp: f"{v:.{d}%}"))
    fig.suptitle("A7 — the confusion that matters, per framing and per prompt. "
                 "Bars are the majority vote of 2 repeats; the grey span above "
                 "each bar is the min–max across those two repeats.",
                 color=MUTED, fontsize=9.5, y=1.01)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_r2_confusion.png"), dpi=95,
                facecolor="white", bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------------------ operating curve
def fig_operating():
    """crop at risk (cost) against weed reached (benefit), as the floor sweeps.

    One axis pair, one path per condition, the shipped floor marked. This is the
    honest form for R2: neither number means anything without the other, and a
    policy is a *point on a curve*, not a score.
    """
    rep = scores()
    conds = [k for k in ("A/r2", "A/neutral", "B/r2", "B/neutral")
             if k in rep["conditions"]]
    fig, ax = plt.subplots(figsize=(9.2, 6.4))
    _tidy(ax)
    for c in conds:
        sw = rep["conditions"][c]["confidence_floor_sweep"]
        floors = sorted(sw, key=float)
        x = [sw[f]["crop_px_at_risk"] for f in floors]
        y = [sw[f]["weed_px_reached"] for f in floors]
        ax.plot(x, y, color=COND_COLOUR[c], lw=2, marker="o", ms=5,
                label=c, zorder=3)
        for f in floors:                       # label the ends only
            if f in ("0.00", "0.95"):
                ax.annotate(f"floor {float(f):.2f}",
                            (sw[f]["crop_px_at_risk"], sw[f]["weed_px_reached"]),
                            textcoords="offset points", xytext=(7, -3),
                            color=MUTED, fontsize=7.5)
    # the baselines, as reference points rather than as curves
    for name, path, mark in (("all-keep (R2's degenerate optimum)",
                              "labels_baseline_all_keep_r0.json", "s"),
                             ("A3 material vote (no VLM)",
                              "labels_baseline_a3_majority_r0.json", "^")):
        b = rep.get("baselines", {}).get(path)
        if b:
            ax.plot(b["crop_px_at_risk"], b["weed_px_reached"], mark, ms=10,
                    color=MUTED, zorder=4)
            ax.annotate(name, (b["crop_px_at_risk"], b["weed_px_reached"]),
                        textcoords="offset points", xytext=(9, 4),
                        color=MUTED, fontsize=8)
    ax.set_xlabel("ground-truth CROP pixels put under the tool  →  catastrophic",
                  color=INK, fontsize=9.5)
    ax.set_ylabel("ground-truth WEED pixels reached  →  the benefit",
                  color=INK, fontsize=9.5)
    ax.xaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.2%}"))
    ax.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_title("A7 — the R2 operating curve: what each framing buys, and what "
                 "it costs\nEach path sweeps the confidence floor below which a "
                 "`remove` is downgraded to `unsure`.",
                 color=INK, fontsize=10.5, loc="left")
    ax.legend(frameon=False, labelcolor=MUTED, fontsize=9,
              title="condition", title_fontsize=9)
    fig.savefig(os.path.join(FIGS, "fig_operating.png"), dpi=95,
                facecolor="white", bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------------------ hard cases
def fig_hard_context():
    """The seedling proxy: the same regions with their context removed."""
    hp = os.path.join(RES, "hard_r2.json")
    if not os.path.exists(hp):
        return
    hard = json.load(open(hp))
    _, comps = load_components()
    lab = {}
    for l in hard["labels"]:
        lab.setdefault((l["condition"], l["id"]), l)
    main = {}
    mp = os.path.join(RES, "labels_A_r2_r1.json")
    if os.path.exists(mp):
        main = {l["id"]: l for l in json.load(open(mp))["labels"]}

    # the regions where taking the context away changed the answer, first
    ids = sorted(set(i for (_, i) in lab if i < 900))
    flipped = [i for i in ids
               if main.get(i) and lab.get(("p000", i))
               and main[i]["label"] != lab[("p000", i)]["label"]]
    show = (flipped + [i for i in ids if i not in flipped])[:5]

    rdir = os.path.join(HERE, "renders", "hard")
    adir = os.path.join(HERE, "renders", "A")
    cols = [("p000", "context removed\n(pad 0.00)", rdir, "_p000"),
            ("shipped", "as shipped\n(pad 0.75)", adir, ""),
            ("p300", "context restored\n(pad 3.00)", rdir, "_p300")]
    fig, axes = plt.subplots(len(show), 3, figsize=(11.5, 3.5 * len(show)))
    axes = np.atleast_2d(axes)
    for r, cid in enumerate(show):
        for c, (cond, title, d, tag) in enumerate(cols):
            ax = axes[r, c]; ax.axis("off")
            p = os.path.join(d, f"region_{cid:03d}{tag}.png")
            if os.path.exists(p):
                im = Image.open(p)
                # keep only the marked detail panel (B), the middle third
                w = im.width
                ax.imshow(im.crop((620, 0, 620 + (w - 620) // 2, im.height)))
            l = main.get(cid) if cond == "shipped" else lab.get((cond, cid))
            txt = (f"{l['label']}  ({l['confidence']:.2f})" if l else "—")
            ax.set_title(f"{title}\nregion {cid} · truth "
                         f"{comps[cid].truth} → said {txt}",
                         color=INK, fontsize=8.5)
    fig.suptitle("A7 — the context ablation, the seedling proxy this image "
                 "allows.\nA label that survives losing its surround was read "
                 "off the material; one that flips was read off the context.",
                 color=MUTED, fontsize=9.5, y=1.005)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig_hard_context.png"), dpi=88,
                facecolor="white", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    os.makedirs(FIGS, exist_ok=True)
    fig_stimulus(); print("fig_stimulus.png")
    if os.path.exists(os.path.join(RES, "a7_scores.json")):
        fig_r2_confusion(); print("fig_r2_confusion.png")
        fig_operating(); print("fig_operating.png")
    fig_hard_context(); print("fig_hard_context.png")
