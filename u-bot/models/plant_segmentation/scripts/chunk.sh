#!/usr/bin/env bash
# Print one chunk section from RESEARCH_ROADMAP.md.
#   usage: scripts/chunk.sh A0
set -euo pipefail
id="${1:?usage: chunk.sh <chunk-id>   e.g. chunk.sh A0}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out=$(awk -v id="$id" '
  # chunk headings look like:  ## A1b — Assumed intrinsics, ...
  $0 ~ "^## " id " " { inchunk = 1; print; next }
  inchunk && (/^# / || /^## /) { exit }
  inchunk             { print }
' "$root/RESEARCH_ROADMAP.md")
if [ -z "$out" ]; then
  echo "No chunk '$id' in RESEARCH_ROADMAP.md. Available:" >&2
  grep -oE '^## [A-C][0-9]+b? ' "$root/RESEARCH_ROADMAP.md" | tr -d '#' | tr -s ' ' >&2
  exit 1
fi
printf '%s\n' "$out"
