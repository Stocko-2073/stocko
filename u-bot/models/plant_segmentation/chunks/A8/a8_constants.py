"""A8 — every numeric constant this chunk introduces, with its R1 category.

A8 introduces exactly two, and one of them is an integer count rather than a
threshold. Everything else it uses is imported from the chunk that measured it
(A2's datum sigma, A5's statuses and its (b) extrapolation budget, A6's (b)
clearance placeholder and (a) voxel edge, A7's triage floors).

``test_a8.py`` parses this module and asserts that every module-level numeric
in the A8 code path appears here with a category, and that no identifier in A8
is a spacing- or agronomy-shaped name (the discipline A4, A5 and A6 established).
"""
from __future__ import annotations

# --------------------------------------------------------------------------
# (c) + R2 — the confidence floor for a removal
# --------------------------------------------------------------------------
#: The VLM confidence below which a `remove` is refused.
#:
#: **Category (c) observation + R2.** The value is *not* tuned to separate this
#: image's one crop mislabel from its one real weed — that separation is 0.02
#: wide (A7's component 5 at 0.58 against component 104 at 0.60-0.62) and A7
#: measured the model's repeat-to-repeat confidence spread at 0.052-0.066, so a
#: floor placed inside that window would be fitted to noise. Tuning it against
#: A0 was attempted and **refused**; the refusal, and the sweep that supports
#: it, are in FINDINGS.md § "the floor cannot be tuned on this image".
#:
#: What justifies 0.70 instead is A7's confabulation probe (§4 of its
#: FINDINGS): six regions drawn over ground-truth *pure straw*, prompted
#: identically to real ones, returned 18/18 `keep` at a **mean confidence of
#: 0.70**. The model says 0.70 about a region containing no plant at all.
#: A self-reported confidence below that carries no evidence about anything, so
#: R2's "high confidence" cannot mean less than it. The floor is at the value
#: the model assigns to nothing.
#:
#: Consequence, reported rather than hidden: on `plants.jpeg` this floor admits
#: **zero** targets, because A7's entire measured `remove` band is 0.518-0.625.
#: A8 measured what that costs (one weed instance) and what it buys (nothing —
#: both crop-bearing candidates are already rejected geometrically), and says so.
REMOVAL_CONFIDENCE_FLOOR = 0.70

#: The floors A8 sweeps in every report, so the cliff is visible rather than
#: asserted. Chosen to bracket A7's measured `remove` band and its endpoints.
CONFIDENCE_FLOOR_SWEEP = (0.00, 0.50, 0.55, 0.58, 0.60, 0.62, 0.65,
                          0.70, 0.90)

# --------------------------------------------------------------------------
# (c) + R4 — how many independent looks a removal needs
# --------------------------------------------------------------------------
#: Number of independent VLM repeats that must agree before a `remove` is even
#: considered. **Category (c) observation + R4.** A7 measured that requiring
#: unanimity across 2 repeats removes a third of the catastrophic errors in its
#: weaker conditions (6->4 under A/neutral, 17->12 under B/neutral) for the
#: price of one extra call. It is R4 — prefer looking again over trusting one
#: look — applied to the semantic layer. Not a threshold on a continuous
#: quantity; a count of observations.
MIN_LABEL_REPEATS = 2
