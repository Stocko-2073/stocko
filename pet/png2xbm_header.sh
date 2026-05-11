#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ] || [ $# -gt 3 ]; then
  echo "Usage: $0 <input.png> [output.h] [symbol_prefix]" >&2
  echo "  Defaults: output = <basename>_logo.h, prefix = <basename>_logo" >&2
  exit 1
fi

input=$1
base=$(basename "$input" .png)
output=${2:-${base}_logo.h}
prefix=${3:-${base}_logo}
guard=$(echo "$prefix" | tr '[:lower:]' '[:upper:]')_H

tmp_xbm=$(mktemp -t "${base}.XXXXXX.xbm")
trap 'rm -f "$tmp_xbm"' EXIT

magick "$input" -background white -alpha remove -alpha off -monochrome -negate "xbm:$tmp_xbm"

width=$(awk '/_width/  {print $3; exit}' "$tmp_xbm")
height=$(awk '/_height/ {print $3; exit}' "$tmp_xbm")
bits=$(awk '/^  0x/ {sub(/[ \t]+$/,""); print}' "$tmp_xbm")

{
  echo "#ifndef ${guard}"
  echo "#define ${guard}"
  echo
  echo "#define ${prefix}_width ${width}"
  echo "#define ${prefix}_height ${height}"
  echo "static const unsigned char ${prefix}_bits[] = {"
  echo "${bits}"
  echo "};"
  echo
  echo "#endif"
} > "$output"

echo "Wrote $output (${width}x${height})"
