#!/bin/bash
# A7 — the whole experiment, in cost order, each step independent.
#
# Every step is allowed to fail without taking the others with it. A step that
# dies on a usage limit leaves its completed calls cached (vlm.py refuses to
# cache a transport failure), so re-running this script resumes rather than
# repeats. Check work/run_all.log for which steps did not finish.
set -u
cd "$(dirname "$0")"
PY=../A3/.venv/bin/python
LOG=work/run_all.log
mkdir -p work
echo "=== $(date) starting ===" >> $LOG

step () {
  echo "--- $(date +%H:%M:%S) $* ---" | tee -a $LOG
  if $PY "$@" >> $LOG 2>&1; then
    echo "    ok" | tee -a $LOG
  else
    echo "    FAILED (see $LOG)" | tee -a $LOG
  fi
}

# cheap first: framing B is 2 calls per repeat
step run_a7.py B --variant r2      --reps 2
step run_a7.py B --variant neutral --reps 2
# the headline condition
step run_a7.py A --variant r2      --reps 2 --workers 8
# the prose ablation
step run_a7.py A --variant neutral --reps 2 --workers 8
# hard cases + confabulation probe
step hard.py --variant r2 --reps 2 --workers 8

echo "=== $(date) done ===" >> $LOG
tail -30 $LOG
