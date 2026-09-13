#!/bin/bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
output_dir=${1:-"$script_dir/stl"}
mkdir -p -- "$output_dir"

for part in x_carriage y_carriage tower base_plate z_carriage board_clamp; do
    echo "Exporting $part..."
    openscad -o "$output_dir/$part.stl" \
        -D "print=\"$part\"" "$script_dir/xyz.scad"
done

echo "Exported all six part types (print two board_clamps) to $output_dir"
