"""A7 — prompt construction.

Prompts are assembled from the fragments below and **written to disk verbatim**
for every call that is made (`chunks/A7/prompts/rendered/`), so what the model
actually saw is committed rather than reconstructed.

The design is a 2x2, on purpose:

|            | `neutral` cost prose | `r2` cost prose |
|---|---|---|
| framing **A** — one call per region | A/neutral | A/r2 |
| framing **B** — one global description, then one binding call | B/neutral | B/r2 |

The *only* textual difference between `neutral` and `r2` inside a framing is the
`COST_*` paragraph, and the two paragraphs are deliberately the same length and
the same register.  A3 measured that rewriting prompt prose moved one specific
confusion 5x while the aggregate stayed flat; matching length is what makes the
resulting difference attributable to the asymmetry claim rather than to verbosity.

R3 is stated in the schema fragment *and* enforced by `schema.py` after the
fact.  The prompt asking for no coordinates is not the safety mechanism.

**The prompt must not name the answer.**  `test_prompt_never_names_the_crop_or_
the_weeds` greps every fragment for `squash`, `kabocha`, `clover`, `grass`,
`straw`, `broadleaf` and friends.  The first draft of `SCHEMA_COMMON` failed it:
it illustrated the `mixed` field with "for example crop leaf and grass blades
together", which hands the model the single fact this chunk exists to test —
whether it notices unaided that the crop component is 83 % grass by A4's
accounting.  Every call in the shipped experiment uses the de-leaked wording;
the leaked draft's one completed repeat was discarded rather than reported,
because a primed answer to the chunk's headline question is worse than no answer.
"""
from __future__ import annotations

import os

HERE = os.path.dirname(os.path.abspath(__file__))
RENDERED = os.path.join(HERE, "prompts", "rendered")

TASK_CORE = """\
You are looking at a photograph of one bed in a home vegetable garden. A
segmentation system has already divided the plant material in that photograph
into numbered regions. Your job is the semantic half of weeding, and only that
half: decide what each region *is*, so that a machine can later decide what to
do about it.

For each region you are shown, choose exactly one label:

  keep    - the material in this region belongs to a plant the gardener is
            growing on purpose, or is something a weeding tool must not cut.
  remove  - the material in this region is a weed: a plant growing here that
            the gardener did not plant and does not want.
  unsure  - you cannot tell which of the two it is from what you were shown.

A region may be a whole plant, a part of a plant, or a patch of material that
belongs to more than one plant. Say so in the `mixed` field when it happens.
"""

COST_NEUTRAL = """\
Treat the two possible mistakes as equally costly. Calling a crop plant a weed
and calling a weed a crop plant are both simply errors, and neither is worse
than the other. Answer with whichever label the visual evidence best supports,
and use `unsure` only when you genuinely cannot tell the two apart.
"""

COST_R2 = """\
The two possible mistakes are not equally costly. Destroying a crop plant is
catastrophic and cannot be undone; leaving a weed standing until the next pass
costs the gardener almost nothing. So the answer defaults to `keep`: unless the
visual evidence positively supports `remove`, answer `keep` or `unsure`.
"""

SCHEMA_COMMON = """\
Output rules, which are strict:

* Reply with JSON and nothing else. No prose before or after, no code fence.
* You must not output coordinates, pixel positions, bounding boxes, directions,
  distances, or measurements of any kind, anywhere in your reply, including
  inside `reason`. The region number is the only handle you are given on the
  image, and it is the only one you may use. A reply containing a coordinate is
  rejected outright.
* `confidence` is a number from 0.00 to 1.00: how sure you are of the label you
  chose.
* `reason` is one line, at most 140 characters, saying what you saw.
* `mixed` is true when the outlined region clearly contains plant material of
  more than one kind, that is, material from more than one plant or more than
  one species, false otherwise. `mixed_note` is at most 100 characters, or ""
  when mixed is false.
"""

A_BODY = """\
You are shown ONE region: region {cid}.

The image has three panels, left to right:

  A  the whole photograph, with every pixel belonging to region {cid} tinted
     magenta, and a magenta rectangle around the area panels B and C show.
  B  a zoom on that area, with region {cid} outlined in magenta and tinted
     magenta.
  C  exactly the same zoom as panel B, with nothing drawn on it, so you can see
     the material as it really looks.

The magenta is drawn by the segmentation system. It is not a plant, and there
is nothing magenta in this garden.

Reply with exactly this JSON object:

{{"id": {cid}, "label": "keep"|"remove"|"unsure", "confidence": 0.00,
  "reason": "...", "mixed": false, "mixed_note": ""}}
"""

B_SCENE_BODY = """\
You are shown the whole garden bed: an overview panel, then {n_tiles} tiles that
together cover the same photograph at full resolution.

Describe this scene. What is being grown here on purpose, and what is growing
here that was not planted? Name the crop as precisely as the photograph
supports, and name each kind of unwanted plant you can see, with the visual
features that tell it apart from the crop. Also note anything present that is
not a living plant.

There are no region numbers in these images and none are being asked for.

Reply with exactly this JSON object:

{{"crop": {{"name": "...", "distinguishing_features": "..."}},
  "weeds": [{{"name": "...", "distinguishing_features": "..."}}],
  "non_plant_material": ["..."],
  "hard_to_tell_apart": "...",
  "scene_notes": "..."}}
"""

B_BIND_BODY = """\
Earlier, looking at this same photograph, you described the scene as follows.

--- your scene description ---
{scene}
--- end of scene description ---

Now you are shown the same bed again: an overview panel, then {n_tiles} tiles at
full resolution. This time every region the segmentation system found is
outlined in magenta and stamped with its region number in yellow. The magenta
and the yellow are drawn by the segmentation system; there is nothing magenta or
yellow in this garden.

Using the description above as your account of what is in this bed, give a label
to EVERY one of the {n_ids} regions listed below. Not some of them: every one. A
region you cannot find or cannot judge gets `unsure` - it does not get left out.

Region numbers to label, all {n_ids} of them:
{id_list}

Reply with exactly this JSON object:

{{"labels": [
   {{"id": 0, "label": "keep"|"remove"|"unsure", "confidence": 0.00,
     "reason": "...", "mixed": false, "mixed_note": ""}},
   ... one entry for each of the {n_ids} region numbers, in the order listed ...
]}}
"""

READ_LINE = ("First, read these image files:\n{files}\n"
             "Do not use any tool other than reading those files.\n")


def _cost(variant):
    return {"neutral": COST_NEUTRAL, "r2": COST_R2}[variant]


def prompt_A(cid, variant, files):
    return "\n".join([READ_LINE.format(files="\n".join(files)),
                      TASK_CORE, _cost(variant), A_BODY.format(cid=cid),
                      SCHEMA_COMMON])


def prompt_B_scene(variant, files, n_tiles):
    return "\n".join([READ_LINE.format(files="\n".join(files)),
                      TASK_CORE, _cost(variant),
                      B_SCENE_BODY.format(n_tiles=n_tiles),
                      "Reply with JSON and nothing else. No prose before or "
                      "after, no code fence. Output no coordinates, pixel "
                      "positions, bounding boxes or measurements of any kind."])


def prompt_B_bind(variant, files, n_tiles, ids, scene):
    id_list = ", ".join(str(i) for i in ids)
    return "\n".join([READ_LINE.format(files="\n".join(files)),
                      TASK_CORE, _cost(variant),
                      B_BIND_BODY.format(scene=scene, n_tiles=n_tiles,
                                         n_ids=len(ids), id_list=id_list),
                      SCHEMA_COMMON])


def save(name, text):
    os.makedirs(RENDERED, exist_ok=True)
    p = os.path.join(RENDERED, name)
    with open(p, "w") as f:
        f.write(text)
    return p
