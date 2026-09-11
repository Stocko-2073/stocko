#!/bin/bash
# Assembly path check. For each step in xyz.scad's asm_steps, the part is swept along its
# insertion path (check_n positions, stopping where a screw's thread enters its hole) and
# intersected with everything fitted before it, using openscad --interference-check. One
# line per step; a step with collisions lists the source lines whose material overlapped,
# with the overlapping volume in mm^3.
#   ./check_assembly.sh                all steps
#   ./check_assembly.sh z_carriage     one step
#   CHECK_U=0.5 ./check_assembly.sh z_carriage    one position along the path
set -euo pipefail
cd "$(dirname "$0")"
out=${CHECK_DIR:-$(mktemp -d)}
mkdir -p "$out"
jobs=${JOBS:-4}

if [ $# -gt 0 ]; then ids="$*"; else
    openscad -o "$out/ids.echo" -D 'echo(asm_ids=[for (s=asm_steps) s[0]])' xyz.scad 2>/dev/null
    ids=$(python3 -c 'import re,sys; s=open(sys.argv[1]).read(); print(" ".join(re.findall(r"\"(\w+)\"", re.search(r"asm_ids = \[(.*?)\]", s).group(1))))' "$out/ids.echo")
fi
extra=(); [ -n "${CHECK_U:-}" ] && extra=(-D "check_u=$CHECK_U")

for id in $ids; do [ "$id" = tower ] || echo "$id"; done | xargs -P "$jobs" -I{} \
    openscad -q --interference-file "$out/{}.json" -o "$out/{}.stl" --export-format binstl \
        -D 'check="{}"' ${extra[@]+"${extra[@]}"} xyz.scad 2>/dev/null

python3 - "$out" $ids <<'PY'
import json, sys, os
out, ids = sys.argv[1], sys.argv[2:]
role = {1: "moving", 2: "fixed"}
bad = 0
for id in ids:
    f = os.path.join(out, id + ".json")
    if not os.path.exists(f):
        print(f"{id:16s} {'(base)' if id=='tower' else 'no report'}"); continue
    r = json.load(open(f))
    cols = r["collisions"]
    vol = sum(c["volume"] for c in cols)
    print(f"{id:16s} {'ok' if not cols else 'COLLIDES':9s} {vol:8.2f}")
    if cols: bad += 1
    seen = {}
    for c in cols:
        for p in c["primitives"]:
            chain = [s for s in p["chain"] if s["location"]]
            where = " > ".join(f"{s['name']}:{s['location']['line']}" for s in chain[-3:]) or p["name"]
            key = (p["part"], where)
            seen[key] = seen.get(key, 0) + p["volume"]
    for (part, where), v in sorted(seen.items(), key=lambda kv: -kv[1])[:8]:
        print(f"{'':16s}   {role.get(part, part):6s} {v:8.2f}  {where}")
print(f"\n{bad} step(s) with collisions; reports in {out}")
PY
