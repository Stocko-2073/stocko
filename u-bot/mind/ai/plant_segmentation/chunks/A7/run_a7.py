"""A7 — run the experiment.

    python run_a7.py render                 # both stimulus sets
    python run_a7.py A  --variant r2 --rep 1
    python run_a7.py B  --variant r2 --rep 1
    python run_a7.py hard --rep 1
    python run_a7.py all                    # every condition, every repeat

Every condition is run `--reps` times with an identical prompt, because the CLI
is non-deterministic and a single run cannot tell a finding from a sample. The
per-run labels are written separately and `score.py` reports the spread.

Triage, and why no ID is dropped. Two tiers, kept apart because they are two
different kinds of claim:

* **tier 1** — below A0's registered 25 px minimum reviewable region. No render
  can carry evidence about it. 78 of 207 components; 0.05 % of the GT crop px.
* **tier 2** — above that but below A7's 75 px call-budget floor. A *money*
  limit, not an evidence one, and labelled as such everywhere. 56 components;
  0.09 % of the GT crop px and 0.00 % of the weed px.

Both are labelled `unsure` by *policy*, in code, with the policy as the
rationale, and both are present in every output file. 73 components are shown
to the model. What tier 2 cost is measured, not argued — see `tier2_audit.py`.
"""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor

import prompts as P
import schema as S
import vlm
from a7_data import load_components
from render import Renderer

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
VARIANTS = ("neutral", "r2")


def ordered_ids(comps):
    """The ids the model is asked about, largest first.

    A stable order with no geometry in it — size only, and size is not a
    coordinate. These are the `core` components (>= TIER1_PX).
    """
    return [c.id for c in sorted(comps.values(), key=lambda c: -c.px)
            if c.core]


def triaged(comps):
    """(id, reason) for every component the model is *not* asked about.

    Two tiers with two different justifications, kept apart on purpose so the
    write-up cannot conflate an evidence limit with a budget limit.
    """
    out = []
    for c in sorted(comps.values(), key=lambda c: -c.px):
        if c.core:
            continue
        if not c.renderable:
            out.append((c.id, "triaged (tier 1): region is below A0's 25 px "
                              "minimum reviewable region, so no render can "
                              "carry evidence about it"))
        else:
            out.append((c.id, "triaged (tier 2): region is above A0's 25 px "
                              "minimum but below A7's 75 px call budget floor, "
                              "so it was not shown to the model"))
    return out


# ---------------------------------------------------------------- framing A
def run_A(comps, variant, rep, workers=8):
    ids = ordered_ids(comps)
    rdir = os.path.join(HERE, "renders", "A")
    def one(cid):
        files = vlm.stage([os.path.join(rdir, f"region_{cid:03d}.png")])
        pr = P.prompt_A(cid, variant, files)
        if cid == ids[0]:
            P.save(f"A_{variant}.txt", pr)
        txt, rec = vlm.call(pr, f"A_{variant}_r{rep}_c{cid:03d}")
        try:
            obj = S.validate_label(S.extract_json(txt), expect_id=cid)
        except S.R3Violation as e:
            obj = S.fallback(cid, f"R3 violation: {e}")
            obj["r3_violation"] = str(e)
        except Exception as e:
            obj = S.fallback(cid, f"unparseable reply: {e}")
        obj["_cost_usd"] = rec.get("cost_usd")
        obj["_wall_s"] = rec.get("wall_s")
        return obj
    with ThreadPoolExecutor(workers) as ex:
        labels = list(ex.map(one, ids))
    for cid, why in triaged(comps):
        labels.append(S.fallback(cid, why))
        labels[-1]["triaged"] = True
    return {"framing": "A", "variant": variant, "rep": rep,
            "model": vlm.MODEL, "cli_version": vlm.cli_version(),
            "prompt_file": f"prompts/rendered/A_{variant}.txt",
            "labels": labels}


# ---------------------------------------------------------------- framing B
def run_B(comps, variant, rep):
    ids = ordered_ids(comps)
    bdir = os.path.join(HERE, "renders", "B")
    plain = sorted(f for f in os.listdir(bdir) if f.startswith("plain_"))
    numb = sorted(f for f in os.listdir(bdir) if f.startswith("montage_"))
    pf = vlm.stage([os.path.join(bdir, f) for f in plain])
    nf = vlm.stage([os.path.join(bdir, f) for f in numb])

    p1 = P.prompt_B_scene(variant, pf, len(pf) - 1)
    P.save(f"B_scene_{variant}.txt", p1)
    t1, r1 = vlm.call(p1, f"B_{variant}_r{rep}_scene")
    try:
        scene = S.extract_json(t1)
        scene_txt = json.dumps(scene, indent=1)
    except Exception as e:
        scene, scene_txt = None, f"[unparseable scene reply: {e}] {t1}"

    p2 = P.prompt_B_bind(variant, nf, len(nf) - 1, ids, scene_txt)
    P.save(f"B_bind_{variant}.txt", p2)
    t2, r2 = vlm.call(p2, f"B_{variant}_r{rep}_bind", timeout=1800)

    got, rejects = {}, []
    try:
        arr = S.extract_json(t2).get("labels", [])
    except Exception as e:
        arr, rejects = [], [f"whole reply unparseable: {e}"]
    for o in arr:
        try:
            v = S.validate_label(o)
        except S.R3Violation as e:
            rejects.append(f"id {o.get('id')}: R3 {e}")
            continue
        except Exception as e:
            rejects.append(f"id {o.get('id')}: {e}")
            continue
        if v["id"] in got:
            rejects.append(f"id {v['id']}: duplicate entry")
            continue
        got[v["id"]] = v

    labels = []
    for cid in ids:
        if cid in got:
            labels.append(got[cid])
        else:
            labels.append(S.fallback(
                cid, "framing B did not return a label for this id"))
            labels[-1]["omitted_by_model"] = True
    extra = sorted(set(got) - set(ids))
    for cid, why in triaged(comps):
        labels.append(S.fallback(cid, why))
        labels[-1]["triaged"] = True
    return {"framing": "B", "variant": variant, "rep": rep,
            "model": vlm.MODEL, "cli_version": vlm.cli_version(),
            "prompt_file": f"prompts/rendered/B_bind_{variant}.txt",
            "scene": scene, "scene_raw": t1,
            "n_returned": len(got), "n_asked": len(ids),
            "omitted": [i for i in ids if i not in got],
            "hallucinated_ids": extra, "rejects": rejects,
            "cost_usd": (r1.get("cost_usd") or 0) + (r2.get("cost_usd") or 0),
            "labels": labels}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render", "A", "B", "all"])
    ap.add_argument("--variant", default="r2", choices=list(VARIANTS) + ["both"])
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    os.makedirs(RES, exist_ok=True)

    if a.cmd == "render":
        R = Renderer()
        out = os.path.join(HERE, "renders", "A")
        ids = ordered_ids(R.comps)
        for i, cid in enumerate(ids):
            R.render_instance(cid, out)
        print(f"A: {len(ids)} region renders")
        ps = R.render_montage(os.path.join(HERE, "renders", "B"))
        print(f"B: {len(ps)} numbered panels")
        return

    _, comps = load_components()
    vs = VARIANTS if a.variant == "both" else (a.variant,)
    cmds = ("A", "B") if a.cmd == "all" else (a.cmd,)
    for f in cmds:
        for v in vs:
            for rep in range(1, a.reps + 1):
                out = (run_A(comps, v, rep, a.workers) if f == "A"
                       else run_B(comps, v, rep))
                p = os.path.join(RES, f"labels_{f}_{v}_r{rep}.json")
                json.dump(out, open(p, "w"), indent=1)
                n = {"keep": 0, "remove": 0, "unsure": 0}
                for l in out["labels"]:
                    n[l["label"]] += 1
                print(f"{f}/{v}/r{rep}: {n}  -> {os.path.basename(p)}",
                      flush=True)


if __name__ == "__main__":
    main()
