# Postmortem: laying out the U-BOT base board with `stripboard` 0.1.1

Notes from designing `ubot_base.py`, written for whoever works on the library
next. The board is a XIAO ESP32-C6, two TMC2209 sticks, six resistors, a cap,
and seven connectors: 40 nets after the router synthesises one per open pin,
on 28 x 22 holes. It routed and validated in the end, but it took eight
iterations, and most of the time went into working out by hand things the
tool knew and did not say.

The short version: the router is a good validator and a fair optimiser, but a
poor explainer. Every failure was reported as `no collision-free route found`
and every cause turned out to be a rule I had to find by reading the source.


## What happened, in order

| # | change | result |
|---|---|---|
| 1 | first layout, resistors unlocked | 24/34 routed, 36 s |
| 2 | locked all parts, fixed same-row conflicts | 34/36, 3V3 and VM unrouted |
| 3 | rebuilt the layout so no net needed a detour row | 34/36, EN and GND unrouted |
| 4 | added a GND/3V3 header on the top rows | same |
| 5 | moved the EN pull-up to bridge rows 11 and 12 | 34/36, 3V3 and BATT unrouted |
| 6 | split MS1 strap off 3V3 as its own net via a hand link | 36/37, BATT unrouted |
| 7 | placed the BATT hop as a hand link | 37/38, GND unrouted |
| 8 | placed two GND hops as hand links | 40/40, valid |

Each step needed a debugging script that routed single nets in isolation,
dumped the strips and jumpers the full solve had chosen, and bisected a net by
dropping one pin at a time. None of that is available from the CLI or the
`Result`.


## Struggles

Ordered by how much time each cost.

### 1. The router cannot say why a net failed

Every unrouted net reports `no collision-free route found`. The information
that would have resolved each case in a minute existed inside the solver:

- which pairs of the net's rows have no feasible jumper column at all;
- which topology class was tried (all trees, or the curated set) and how many
  were rejected for geometry versus budget;
- whether the detour-row fallback ran, which rows it considered, and why each
  was rejected;
- for a column that would have worked, which other net's jumper or which
  keep-out occupies it.

Suggest a `route_report(verbose=True)` or `Result.explain(net_id)` that prints
the feasibility matrix over the net's rows, and a CLI `stripboard explain
board.py --net GND` that routes one net against the fixed geometry. The two
scripts I ended up writing (`dbg.py`, `dbg2.py` in the scratch area) are that
feature in twenty lines each; they belong in the package.

### 2. One strip per row per net is a hard rule, and nothing says so

Two pins of a net on the same row with a foreign pin between them can never
route: the row gets one strip and it would have to cover the foreign pin. My
first layout had three such rows (encoder GND pins at columns 2 and 22 on the
same row as two open XIAO pins, and the same for 3V3). This is checkable in
`resolve()` before any routing happens, with a precise message:

    net GND: pins (2,14) and (22,14) share row 14 but foreign pin (5,14)
    lies between them; a row carries one strip per net

Better still, lift the rule: a second strip on the same row is just another
node in the spanning tree, reached by a jumper like any other row. The data
model (`Strip` per row) does not require uniqueness, only `pins_by_row` does.

### 3. Nets over five rows get a curated topology set that misses real shapes

`_route_all_topologies` enumerates every spanning tree for k <= 5 rows, and
for larger k falls back to `_curated_trees`: the chain in row order, a star
per hub, and double-stars split on a prefix of the sorted rows. The 3V3 net
had seven rows and a perfectly good tree (a path 13-6-2-5-12 with two leaves
on 12), and none of the curated shapes fit, so it failed even when routed
alone with nothing else on the board. Dropping any one pin made it route.

The fix is to enumerate over the feasibility graph, not over abstract shapes.
Row pairs with at least one feasible column are known before the search; the
graph for a 7-row net here had about ten edges, and its spanning trees are few.
Prufer enumeration on the feasibility graph, or DFS/BFS trees from each root,
would have found the answer immediately. If a cap is still wanted, 16807 trees
for k=7 is cheap given the per-topology branch-and-bound already prunes.

### 4. The detour-row fallback almost never helps

`_route_steiner_fallback` tries one extra row, chosen from
`_steiner_row_candidates`: rows the net has no pins on, sorted interior rows
first then by row number, capped at six. Three consequences on a real board:

- a net spanning more than six interior rows never gets to try an exterior
  row, so the empty rows at the board edges, which are exactly where a bus can
  cross, are never candidates. GND with pins on rows 4 and 20 could only ever
  try rows 7 to 12, all of them full;
- interior candidates are ranked by row number, not by whether the row has any
  free span in the columns the net needs;
- one detour row is often not enough for the power nets on a board with three
  modules; VM needed two here.

Suggest ranking candidate rows by usable span within the net's column range,
including exterior rows, and allowing two detours for nets over k rows.

### 5. Rip-up does not attribute conflicts

The left edge had three free columns and five vertical hops to fit (BATT,
GND twice, 3V3, VM), with exactly one legal assignment. Sixty attempts of
reordering plus congestion history never found it; a different net lost each
time. `route_nets` reorders failed nets to the front and shuffles, but it does
not know *which* placed jumper blocked the failing net, so it cannot rip up
that one and retry. PathFinder-style negotiation needs the conflict
attribution, and the occupancy index already records the owner of every
occupied cell (`Occupant.key`), so the information is there.

A cheaper win: when several columns tie on cost for a jumper, prefer the one
that appears in the fewest other nets' feasible column sets. That single
lookahead would have solved the left edge without any rip-up.

### 6. Unlocked placement is not routability-aware in practice

Letting the router place the eight resistors (`locked=False`) produced an
unroutable board every time, in 36 s, because HPWL put pull-ups in the gap
columns the big nets needed for jumpers. `place_candidates` is described as
routability-ranked, but with eight small parts the ranking did not help.

The observation that would fix it: a two-pin part between two nets is a
jumper with a body. Pull-ups, series resistors and decoupling caps all want to
sit exactly where a jumper between their two nets' strips would go. Placing
them *during* routing, as jumper candidates with a keep-out, instead of before
it, would make `locked=False` useful for the most common unlocked parts.

### 7. Module footprints have no body keep-out

`dip()` and `xiao()` register pins only, so the router will put a jumper end
under a module body. `terminal()`, `resist()` and `big_button()` do register
keep-outs, so the inconsistency is surprising. I added `sb.keepout()` calls
for the interior columns of each module and for the XIAO's USB-C overhang by
hand. Suggest a `body_keepout=True` default on DIP-style footprints, and
connector-overhang rectangles on the module footprints that have them.

### 8. No public way to place a wire the router respects

Four wires had to be hand-placed. `sb.jumper()` draws one but the router does
not see it; I reached for `sb._register()` to give it pins and a keep-out
(`link()` in `ubot_base.py`). Two API gaps:

- a builder such as `sb.link(x, y1, y2)` returning a `Component` whose ends
  are pins and whose span is a keep-out, so hand routing and autorouting can
  mix safely. Today `jumper()`, `cut()` and `autoroute()` on the same board are
  a silent collision risk and nothing in the docs warns about it;
- the router should honour internal ties when building the tree. `rows =
  sorted(pins_by_row)` gives k rows and k-1 jumpers regardless of ties, so a
  tied link between two rows cannot reduce the jumper count. That forced me to
  split GND into three nets and 3V3 into two purely to get the geometry past
  the router, which is the wrong reason to edit a netlist.

### 9. Strips are stretched to the board edges

`minimize_cuts` extends every strip until it hits a foreign point or the edge,
because a cut costs 3 and copper costs nothing. Six strips on this board run
the full 28 holes: GND, 3V3, UART, EN, the battery divider tap, and VM. It is
electrically fine, but the battery-sense strip now runs the width of the board
under the 12 V terminal, and every later modification has to cut into
something. A `trim` option, or a small cost per strip hole past the last pin
or jumper, would keep the board editable. The rows the router picks as hubs
also matter: 3V3 took all of row 11 because the EN pull-up's 3V3 end sat
there, and that was EN's only crossing row. Nothing wrong with the choice by
the cost function, but a report of "row 11 is now fully occupied by 3V3" would
have pointed me at the fix.

### 10. The DESIGN view does not colour autorouted nets

`docs/coordinates.md` and the README describe DESIGN as flood-filled per net.
That only happens through manual `trace()` calls; `autoroute()` colours its
jumpers and nothing else, so the strips stayed grey and I checked
connectivity by reading `Result.routing.strips` instead of by eye. Having
`_render_routing` call `trace()` from one pin of each net, with the net's
colour, would make the view match the docs.

### 11. Small things

- Pin order in `dip(pins=...)` is "left column top to bottom, then right column
  bottom to top". It is documented only on `_dip_pins`; I probed it with a
  throwaway script. Same for `resist()` pin 1 being the top hole and
  `upside_down` swapping it. Both belong in the public docstrings and the
  README.
- `keepout()` defaults to `show=False` but its docstring says shading is the
  default.
- `xiao()` says "XIAO RP2040" in its comment; the pin map fits the whole XIAO
  family and the label should say so.
- `cap()` marks + at pin 1, and `upside_down=True` draws the mark mid-body for
  `l=2`. A `polarity` flag that moves the mark to the right pin would be
  clearer.
- `sip()` labels overlap neighbouring parts at the default scale; the encoder
  headers next to their pull-ups became unreadable. A `labels=False` option,
  or clipping against the board, would help.
- A StepStick footprint with named pins would be a natural addition to
  `footprints/modules.py`; two of them are on this board and they are on most
  hobby motion boards.
- `project(report=True)` prints counts only. Per-net jumper lists, total wire
  length, and cuts under module bodies (23 of 34 here, which matters for build
  order) are all one loop over `Result`.


## What worked well

- Zero dependencies and fast solves: 1.6 to 7 s per run once parts were
  locked. Iteration cost was the analysis, never the tool.
- Deterministic results across seeds, and a validator that runs on every
  solve. Knowing the final board is checked against nine rules is the reason
  the hybrid hand-link approach felt safe.
- Open pins are isolated automatically. Fourteen NC pins on this board and I
  never thought about their cuts.
- Footprint pin maps as the single source of truth, and `Component.pin()`
  raising with the list of valid names. The KeyError message is exactly right.
- `project()` running `draw` several times against one cached solve. The
  build sheet, label and design page all agree by construction.
- The mirrored BACK view. That is the view a board actually gets built from.
- Enough is exposed on `StripBoard` and `Result` that all of the debugging
  above was possible without patching the library.


## Suggested order of work

1. Diagnostics: feasibility matrix per failed net, and a single-net explain
   mode. Highest value per hour by a wide margin.
2. Pre-route netlist checks for same-row conflicts, with the message above.
3. Topology enumeration over the feasibility graph instead of curated shapes.
4. A public `link()` builder, and internal ties honoured by the tree search.
5. Body keep-outs on module footprints by default.
6. Detour candidates ranked by usable span, exterior rows included.
7. Least-contested-column tie-breaking, then conflict-attributed rip-up.
8. Two-pin unlocked parts placed as jumpers during routing.
9. DESIGN view colouring from `autoroute()`, and strip trimming as an option.
