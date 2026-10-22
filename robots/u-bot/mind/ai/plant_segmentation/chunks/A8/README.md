# A8 — MCP tool surface and the safety gate

Two MCP tools over the Phase A stack. `segment_garden` returns geometry with no
crop/weed opinion; `plan_removals` applies R2's asymmetry **in code** and
returns an ordered target list plus a rejection report over a closed
twelve-reason vocabulary. It ends at a target
list: nothing here plans or commands motion.

Read `FINDINGS.md` first. The one-line result: on `plants.jpeg` the shipped
configuration admits **0 targets**, the diagnostic floor-0.00 configuration
admits **1**, and **no ground-truth crop pixel is under the tool at any floor**
— because the keep-out test, not the confidence floor, is what refuses A7's
mislabels.

## Layout

| file | what it is |
|---|---|
| `a8_common.py` | loading, and the three integration seams (split→merge, crop identity, scale) |
| `a8_constants.py` | the two constants A8 introduces, with R1 categories |
| `a8_gate.py` | the gate. R2 as a data structure. Closed rejection vocabulary |
| `a8_tools.py` | the two tools and their JSON schemas |
| `server.py` | MCP over stdio, standard library only |
| `client.py` | minimal MCP stdio client (subprocess + pipes) used by the run and the tests |
| `mcp_sdk_client.py` | conformance: the **official** `mcp` SDK driving `server.py` |
| `build_products.py` | precompute the instance table and the 531 × 207 keep-out distance table (39 s) |
| `run_a8.py` | the end-to-end run, entirely over the wire |
| `analyse.py` | the ablation — which condition carries the safety |
| `figures.py` | `figs/fig_gate.png`, `figs/fig_operating.png` |
| `test_a8.py` | 31 tests, 2.4 s |

Products: `products/segment_garden_plants.json`, `products/target_list.json`,
`products/rejection_report.json`,
`products/target_list_floor000_diagnostic.json`,
`products/keepout_distances.npz`, `products/gt_audit.json` (ground truth, for
scoring only — no tool reads it). Results: `results/a8_scores.json`,
`results/a8_ablation.json`, `results/mcp_conformance.json`.

## Reproduce

```bash
cd /path/to/plant_segmentation
V=chunks/A3/.venv/bin/python          # UNCHANGED from A3; A8 adds no package

$V chunks/A8/build_products.py        # ~40 s, ~3.5 GB peak (one big instance)
$V chunks/A8/run_a8.py                # ~1 s, end-to-end through the server
$V chunks/A8/analyse.py               # the ablation table
$V chunks/A8/figures.py               # both figures
$V -m pytest chunks/A8/test_a8.py -q  # 31 passed in ~2.4 s
```

MCP conformance, in its own client-only venv (created once):

```bash
uv venv chunks/A8/.venv-client --python 3.11
uv pip install --python chunks/A8/.venv-client/bin/python mcp   # mcp 2.1.1
chunks/A8/.venv-client/bin/python chunks/A8/mcp_sdk_client.py   # -> "verdict": "PASS"
```

## Using the server

```bash
chunks/A3/.venv/bin/python chunks/A8/server.py    # JSON-RPC 2.0 on stdin/stdout
```

`initialize` → `tools/list` → `tools/call`. Register it with any MCP host as a
stdio server with that command. The flow is:

1. `segment_garden({"image": "…/plants.jpeg"})` → 207 instances with ids.
2. Label the instances **by id**, more than once, from independent looks. Never
   by coordinate (R3).
3. `plan_removals({"labels": [...], "tool_profile": {"clearance": 0.01,
   "clearance_units": "rdu"}})` → targets + rejections.

Supplying one look per instance is refused (`insufficient_repeats`). Supplying
a clearance in millimetres is refused (`metric_tool_profile_refused`) — this
image has no absolute scale and A8 will not invent one.

## What travels with every output, and must not be stripped

* **`scale_confidence: "scale_free"`.** Every length is in rdu. There is no
  metre in this product.
* **The datum is the STRAW mulch surface, not soil.** A contact point is a
  point on the mulch; the straw depth is unmeasured.
* **`contact_status` is the safety field.** `geometry_confidence` (A5) and the
  label confidence (A7) are orderings, not probabilities.
* **A `keep` may mean "there is nothing here to cut"**, not "this is crop"
  (A7's vocabulary gap).
