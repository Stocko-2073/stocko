# Constants register

Enforcement mechanism for **R1**. Every numeric constant in the pipeline is
listed here with the category that justifies it:

- **(a) Instrument** — sensor noise, depth quantisation, calibration residual.
- **(b) Tool geometry** — kerf, clearance, reach, positioning repeatability.
- **(c) Observation** — measured in this scene, this visit, or a prior visit.
- **(d) Assumed, with a documented sensitivity bound** — only where (a)–(c) are
  genuinely unavailable. **Requires a sweep.** Must name the chunk that retires it.

A constant with no category is a defect. A (d) constant with no sweep is a
defect. No constant may encode a belief about how gardens are arranged, how far
apart plants grow, or how large a crop gets.

Append a row when you introduce a constant. Do not delete rows — when a
constant is retired, set **Retired by** and move it to the Retired table.

## Active

| Chunk | Name | Value | Cat | Justification | Sweep | Retired by |
|---|---|---|---|---|---|---|
| A0 | instance match IoU | 0.5 | (c) | Stated convention for instance matching; documented and swappable in `eval.py`. | n/a | — |
| A1b | `f` initial | 3005 px | (d) | 26 mm-equiv phone main camera at 3000×4000, via `f_px = f_eq × diag_px / 43.27 mm`. Camera unavailable, EXIF stripped. | **required** — `f ∈ {1502, 2774, 3005, 3236, 6009}` | C0 |
| A1b | principal point | image centre (1500, 2000) | (d) | No calibration available. | **required** — with `f` sweep | C0 |
| A1b | distortion | zero | (d) | Phone ISPs pre-correct most lens distortion. | **required** — bound the residual | C0 |
| A1b | absolute scale | **unresolved** | — | Deliberately unassigned. No fiducial, no known dimension. Inferring it from plant size would violate R1. Phase A is written scale-free. | n/a | C0 |

## Retired

| Chunk | Name | Old value | New value | Cat | Retired by |
|---|---|---|---|---|---|
| _(none yet)_ | | | | | |

## Audit

Run before declaring any chunk done:

```bash
# (d) constants missing a sweep
grep -n '| (d) |' CONSTANTS.md | grep -v 'required'
# constants in code that never made it into the register
grep -rnE '=\s*-?[0-9]+\.?[0-9]*' --include='*.py' chunks/ | grep -v test
```

The second query is deliberately noisy. Skim it; the point is to catch the
constant someone inlined at 2am and never registered.
