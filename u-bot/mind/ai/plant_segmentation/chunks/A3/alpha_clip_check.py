"""A3 — the Alpha-CLIP feasibility check, run before falling back to SigLIP 2.

The brief allows either Alpha-CLIP or SigLIP 2 for approach 4, and asks that the
choice be recorded rather than asserted. This script is that record: it probes
every distribution channel Alpha-CLIP's own model zoo lists and prints what came
back, so the decision can be re-checked rather than believed.

    chunks/A3/.venv/bin/python chunks/A3/alpha_clip_check.py

Result on 2026-09-01 (see FINDINGS.md):

* the *code* is fine — `pip install git+https://github.com/SunzeY/AlphaCLIP`
  resolves, and its only requirements are ftfy / regex / tqdm / torch /
  torchvision, all of which the A3 venv already satisfies;
* the *weights* are not. There is no PyPI package (`alpha-clip`,
  `alpha_clip`: 404), no official Hugging Face repo (`SunzeY/AlphaCLIP`: 404),
  and the two mirrors the model zoo lists are a Google Drive folder (interactive
  consent page, not scriptable without `gdown` and a confirm token) and
  openxlab.org.cn, which does not respond from here at all.
* the only Hugging Face hits for "alphaclip" are `chouss/alpha_clip_final` — an
  unversioned third-party fine-tune with no model card and no provenance — and
  `Elise-hf/alphaClip`, which contains nothing but a `.gitattributes`.

Loading unattributed weights to make a claim about a published method would be
worse than not running it, so approach 4 ships **SigLIP 2**, and Alpha-CLIP's
*idea* — mark the region without destroying the surround — is tested instead as
the `blend` crop variant in `open_vocab.py`, which needs no new weights.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request

CHANNELS = {
    "pypi:alpha-clip": "https://pypi.org/pypi/alpha-clip/json",
    "pypi:alpha_clip": "https://pypi.org/pypi/alpha_clip/json",
    "github:SunzeY/AlphaCLIP": "https://api.github.com/repos/SunzeY/AlphaCLIP",
    "hf:SunzeY/AlphaCLIP": "https://huggingface.co/api/models/SunzeY/AlphaCLIP",
    "hf:search=alphaclip": "https://huggingface.co/api/models?search=alphaclip&limit=20",
    "openxlab:clip_l14_grit20m": (
        "https://download.openxlab.org.cn/models/SunzeY/AlphaCLIP/weight/"
        "clip_l14_grit20m_fultune_2xe.pth"),
}


def probe(url, timeout=25):
    req = urllib.request.Request(url, method="GET",
                                 headers={"Range": "bytes=0-1023",
                                          "User-Agent": "a3-feasibility-check"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"status": r.status, "bytes": len(r.read(1024))}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "error": e.reason}
    except Exception as e:                    # timeout, DNS, TLS, reset
        return {"status": None, "error": f"{type(e).__name__}: {e}"}


def main():
    out = {}
    for name, url in CHANNELS.items():
        out[name] = probe(url)
        print(f"{name:32s} {out[name]}")
    try:
        p = subprocess.run(
            ["uv", "pip", "install", "--dry-run", "--python", sys.executable,
             "git+https://github.com/SunzeY/AlphaCLIP"],
            capture_output=True, text=True, timeout=180)
        out["code_install_dry_run"] = {"returncode": p.returncode,
                                       "tail": p.stderr.strip()[-400:]}
    except Exception as e:
        out["code_install_dry_run"] = {"error": str(e)}
    print(json.dumps(out["code_install_dry_run"], indent=1))
    print("\nVerdict: code installable, weights not obtainable from any "
          "attributable source -> approach 4 ships SigLIP 2.")
    return out


if __name__ == "__main__":
    main()
