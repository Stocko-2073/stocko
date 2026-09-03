"""A7 — the output contract, and R3 enforced in code.

R3 says the VLM labels instances by ID and never emits coordinates. The prompt
asks for that; this module is what *makes* it true. Every reply passes through
`validate_label()`, which:

* accepts only the six permitted keys,
* accepts only the three permitted labels,
* rejects any key whose name is geometric (`x`, `bbox`, `point`, `centroid`, ...),
* and scans the free-text fields for anything that reads as a coordinate or a
  measurement, because a rationale is free text and free text is where a
  coordinate would actually get through.

A reply that fails validation is not silently patched. It is recorded as a
rejection, and the ID it was for falls back to `unsure` with the rejection as
its rationale — R2's default, applied by the code rather than by the model.
"""
from __future__ import annotations

import json
import re

ALLOWED_KEYS = {"id", "label", "confidence", "reason", "mixed", "mixed_note"}
REQUIRED_KEYS = {"id", "label", "confidence", "reason"}
LABELS = {"keep", "remove", "unsure"}

# key names that would carry geometry
BANNED_KEY = re.compile(
    r"^(x|y|z|u|v|cx|cy|row|col|px|py|bbox|box|rect|point|points|coord|coords|"
    r"coordinate[s]?|centroid|center|centre|position|pos|location|loc|mask|"
    r"polygon|contour|extent|offset|pixel|pixels|width|height|area|size|"
    r"distance|dist|angle|bearing)$", re.I)

# Two tiers, deliberately.
#
# HARD — an actual coordinate, box or measurement. This is what R3 exists to
# stop, and it is a rejection.
#
# SOFT — frame-relative prose ("lower left of the frame", "tile 7"). It is a
# location by another name, so it is recorded on every label and counted; it is
# not a rejection, because turning every such reply into `unsure` would silently
# rewrite the label distribution and the experiment would measure the validator
# instead of the model. The counts are reported in FINDINGS.
BANNED_TEXT_HARD = [
    # a coordinate pair: (123, 456) or [123,456] or 123,456 with 2+ digits each
    re.compile(r"[\(\[]\s*\d{2,}\s*,\s*\d{2,}\s*[\)\]]"),
    re.compile(r"\b\d{2,}\s*,\s*\d{2,}\b"),
    # explicit units of length or area
    re.compile(r"\b\d+(\.\d+)?\s*(px|pixels?|mm|cm|m|metres?|meters?|inch|"
               r"inches|ft|feet)\b", re.I),
    # explicit geometry words attached to a number
    re.compile(r"\b(x|y)\s*=\s*-?\d+", re.I),
    re.compile(r"\b(bbox|bounding box|centroid|coordinates?)\b", re.I),
]

# frame-relative directions: a location by another name, recorded not rejected
BANNED_TEXT_SOFT = [
    re.compile(r"\b(top|bottom|upper|lower|left|right|centre|center)[\s-]"
               r"(left|right|half|third|quadrant|corner|edge|side|portion|"
               r"of the (image|frame|photo|panel|tile|scene))\b", re.I),
    re.compile(r"\b(tile|panel)\s*\d+\b", re.I),
]

TEXT_FIELDS = ("reason", "mixed_note")


class R3Violation(ValueError):
    pass


def scan_text(s: str, tier="hard"):
    """Return the first R3-violating fragment in `s` at this tier, or None."""
    pats = BANNED_TEXT_HARD if tier == "hard" else BANNED_TEXT_SOFT
    for pat in pats:
        m = pat.search(s or "")
        if m:
            return m.group(0)
    return None


def validate_label(obj, expect_id=None):
    """Validate one label object. Raises R3Violation / ValueError, or returns it."""
    if not isinstance(obj, dict):
        raise ValueError(f"not an object: {type(obj).__name__}")
    extra = set(obj) - ALLOWED_KEYS
    if extra:
        for k in extra:
            if BANNED_KEY.match(str(k)):
                raise R3Violation(f"geometric key {k!r}")
        raise ValueError(f"unexpected keys {sorted(extra)}")
    missing = REQUIRED_KEYS - set(obj)
    if missing:
        raise ValueError(f"missing keys {sorted(missing)}")
    if obj["label"] not in LABELS:
        raise ValueError(f"bad label {obj['label']!r}")
    try:
        c = float(obj["confidence"])
    except (TypeError, ValueError):
        raise ValueError(f"bad confidence {obj['confidence']!r}")
    if not 0.0 <= c <= 1.0:
        raise ValueError(f"confidence out of range: {c}")
    if expect_id is not None and int(obj["id"]) != int(expect_id):
        raise ValueError(f"id {obj['id']} != expected {expect_id}")
    soft = []
    for f in TEXT_FIELDS:
        hit = scan_text(str(obj.get(f, "")), "hard")
        if hit:
            raise R3Violation(f"{f} contains {hit!r}")
        s = scan_text(str(obj.get(f, "")), "soft")
        if s:
            soft.append(f"{f}:{s}")
    out = dict(obj)
    out["r3_soft"] = soft
    out["id"] = int(obj["id"])
    out["confidence"] = c
    out["mixed"] = bool(obj.get("mixed", False))
    out["mixed_note"] = str(obj.get("mixed_note", ""))
    out["reason"] = str(obj["reason"])
    return out


def extract_json(text: str):
    """Pull the first complete JSON object out of a reply."""
    if text is None:
        raise ValueError("empty reply")
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    depth, start = 0, None
    for i, ch in enumerate(t):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(t[start:i + 1])
                except json.JSONDecodeError:
                    start = None
    raise ValueError("no JSON object in reply")


def fallback(cid, why):
    """R2's default, applied in code: an ID we cannot defend is `unsure`."""
    return {"id": int(cid), "label": "unsure", "confidence": 0.0,
            "reason": f"[code fallback] {why}", "mixed": False,
            "mixed_note": "", "fallback": True}
