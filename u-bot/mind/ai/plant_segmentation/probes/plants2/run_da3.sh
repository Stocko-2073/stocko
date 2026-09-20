#!/bin/bash
# Depth Anything 3 on plants2.jpeg: the two A1 products (nested-giant @504, @1344)
# plus the other runs A1 found camera-consistent (@700, da3-large @504/@700),
# so the camera head's focal estimate can be compared with plants.jpeg.
set -u
cd "$(dirname "$0")/../../chunks/A1"
export PYTORCH_ENABLE_MPS_FALLBACK=1
P=../../probes/plants2
while read -r m r; do
  echo "=== $m res $r $(date +%H:%M:%S)"
  .venv/bin/python da3_infer.py --model "$m" --res "$r" --image ../../plants2.jpeg \
     --outdir "$P/chunks/A1/depth/${m}_res$r" 2>&1 | grep -v "WARN\|warn" | tail -6
done <<LIST
da3nested-giant-large 504
da3nested-giant-large 1344
da3nested-giant-large 700
da3-large 504
da3-large 700
LIST
echo "=== ALL DONE $(date +%H:%M:%S)"
