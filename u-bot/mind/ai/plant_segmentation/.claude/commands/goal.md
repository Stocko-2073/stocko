---
description: Load a research chunk brief from RESEARCH_ROADMAP.md and start work on it
argument-hint: <chunk-id>   e.g. A0, A1b, A4
allowed-tools: Bash(./scripts/chunk.sh:*), Bash(grep:*), Read, Edit, Write, Glob, Grep
---

## Chunk brief: $ARGUMENTS

!`./scripts/chunk.sh $ARGUMENTS`

---

## Current state

!`grep -E "^\| $ARGUMENTS \|" PROGRESS.md || echo "(chunk not in the PROGRESS.md status table — check the id)"`

---

## Your task

Implement the **Goal** block above for chunk `$ARGUMENTS`.

Before starting:

1. Check the chunk's dependencies are `done` in `PROGRESS.md`. If they are not,
   stop and say so rather than working around them.
2. If the chunk is marked `blocked`, it needs hardware or data we do not have.
   Stop and say what is missing.
3. Set the chunk to `in progress` in the `PROGRESS.md` status table.

While working:

- Respect **R1–R4** in `CLAUDE.md`. Every numeric constant you introduce gets a
  row in `CONSTANTS.md` with its category. If you cannot justify a constant
  under (a), (b) or (c), it is (d) and it needs a sensitivity sweep.
- Put artifacts in `chunks/$ARGUMENTS/`.
- Honour **Out of scope**. If the work seems to require something listed there,
  raise it rather than quietly expanding.

Finishing — a chunk is done only when all four hold:

1. `chunks/$ARGUMENTS/FINDINGS.md` written, using `chunks/TEMPLATE.md`.
2. Scores appended to `RESULTS.md`, compared against the recorded baseline.
3. New constants registered in `CONSTANTS.md`; run the audit queries there.
4. Entry appended to the bottom of `PROGRESS.md`, and the status table updated.

If you could not measure something the chunk asked for, say so explicitly in
FINDINGS.md and RESULTS.md. Do not leave a gap that reads as a pass.
