#!/bin/bash
# A1b — the whole sweep, in the order the README documents.
#
#   bash chunks/A1b/sweep_all.sh a2      # the A2 re-fits (parallel, minutes each)
#   bash chunks/A1b/sweep_all.sh a45     # A4 + A5 on top of them (serial, fast)
#   bash chunks/A1b/sweep_all.sh freeseed  # the free-RANSAC-seed control sweep
#
# Run from <repo>/models/plant_segmentation. `--seed-plane-from` transports A2's
# RANSAC seed plane from the reference row by the exact closed form, so every
# row starts from the same physical plane and only `f` differs. Without it four
# of the nine rows diverge, for a reason that has nothing to do with the focal
# length — see FINDINGS, "the RANSAC seed lottery".
set -u
V1=chunks/A1/.venv/bin/python
V3=chunks/A3/.venv/bin/python
FS=(1502 2774 3005 3236 4159 4453 4489 4695 6009)
REF=chunks/A1b/work/manifest/results/fit_report_primary_raster.json
SEED=(--seed-plane-from "$REF" --seed-plane-fx 4453.214615110367
      --seed-plane-fy 4492.415170820932)
mkdir -p chunks/A1b/work/logs
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
       VECLIB_MAXIMUM_THREADS=1 PYTORCH_ENABLE_MPS_FALLBACK=1

case "${1:-a2}" in
  a2)
    for f in "${FS[@]}"; do
      $V1 -u chunks/A1b/run_stage.py --f "$f" --stage a2 "${SEED[@]}" \
        > chunks/A1b/work/logs/a2_f${f}.log 2>&1 &
    done; wait ;;
  freeseed)
    for f in "${FS[@]}"; do
      $V1 -u chunks/A1b/run_stage.py --f "$f" --stage a2 --tag-suffix _freeseed \
        > chunks/A1b/work/logs/a2_f${f}_freeseed.log 2>&1 &
    done; wait ;;
  a45)
    for f in "${FS[@]}"; do
      $V3 -u chunks/A1b/run_stage.py --f "$f" --stage a45 \
        2>&1 | tee chunks/A1b/work/logs/a45_f${f}.log
    done ;;
  a45freeseed)
    for f in "${FS[@]}"; do
      $V3 -u chunks/A1b/run_stage.py --f "$f" --stage a45 --tag-suffix _freeseed \
        2>&1 | tee chunks/A1b/work/logs/a45_f${f}_freeseed.log
    done ;;
  *) echo "usage: sweep_all.sh {a2|a45|freeseed|a45freeseed}"; exit 2 ;;
esac
echo "done: $1"
