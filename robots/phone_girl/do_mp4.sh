#!/bin/sh
set -eu

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  cat <<'USAGE'
Usage: ./do_mp4.sh [model.scad] [camera] [frames] [audio: 0|1]

Defaults: gynoid.scad, a fixed full-model camera, 288 frames, no audio.
Output: devlog/<model.scad>.<timestamp>.mp4, 60 fps, four loops.
Copy the camera command echoed by OpenSCAD to use your current view.

Environment: NUM_THREADS=10 IMGSIZE=1920,1920 LOOPS=4
             OUTPUT_DIR=devlog AUDIO_FILE=dnb2.mp3
USAGE
  exit 0
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"
MODEL=${1:-gynoid.scad}
CAMERA=${2:-0,0,-33,70,0,25,1150}
NUM_FRAMES=${3:-288}
INCLUDE_AUDIO=${4:-0}
NUM_THREADS=${NUM_THREADS:-10}
IMGSIZE=${IMGSIZE:-1920,1920}
LOOPS=${LOOPS:-4}
OUTPUT_DIR=${OUTPUT_DIR:-$SCRIPT_DIR/devlog}
AUDIO_FILE=${AUDIO_FILE:-$SCRIPT_DIR/dnb2.mp3}

for VALUE in "$NUM_FRAMES" "$NUM_THREADS" "$LOOPS"; do
  case "$VALUE" in
    ''|0|*[!0-9]*) echo "Frames, threads and loops must be positive integers." >&2; exit 1 ;;
  esac
done
case "$INCLUDE_AUDIO" in
  0|1) ;;
  *) echo "Audio must be 0 or 1." >&2; exit 1 ;;
esac
[ -f "$MODEL" ] || { echo "Model not found: $MODEL" >&2; exit 1; }
command -v openscad >/dev/null
command -v ffmpeg >/dev/null
if [ "$INCLUDE_AUDIO" -eq 1 ]; then
  command -v ffprobe >/dev/null
  [ -f "$AUDIO_FILE" ] || { echo "Audio not found: $AUDIO_FILE (set AUDIO_FILE)." >&2; exit 1; }
fi
MODEL="$(CDPATH= cd -- "$(dirname -- "$MODEL")" && pwd)/$(basename -- "$MODEL")"
mkdir -p "$OUTPUT_DIR"
DEST_MP4="$OUTPUT_DIR/$(basename -- "$MODEL").$(date +%Y%m%d%H%M%S).mp4"
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/gynoid-mp4.XXXXXX")
PIDS=""

cleanup() {
  for PID in $PIDS; do
    kill "$PID" 2>/dev/null || true
  done
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

[ "$NUM_THREADS" -le "$NUM_FRAMES" ] || NUM_THREADS=$NUM_FRAMES
echo "Rendering $NUM_FRAMES frames from $MODEL..."
for I in $(seq 1 "$NUM_THREADS"); do
  openscad -q --hardwarnings \
    --animate "$NUM_FRAMES" --animate_sharding "$I/$NUM_THREADS" \
    --imgsize "$IMGSIZE" --colorscheme Starnight --camera "$CAMERA" \
    -o "$WORK_DIR/frame.png" "$MODEL" &
  PIDS="$PIDS $!"
done
FAILED=0
for PID in $PIDS; do
  wait "$PID" || FAILED=1
done
PIDS=""
[ "$FAILED" -eq 0 ] || { echo "Rendering failed." >&2; exit 1; }
set -- "$WORK_DIR"/frame*.png
[ -f "$1" ] && [ "$#" -eq "$NUM_FRAMES" ] || { echo "Incomplete frame sequence." >&2; exit 1; }

ffmpeg -hide_banner -loglevel warning -framerate 60 -pattern_type glob \
  -i "$WORK_DIR/frame*.png" -c:v libx264 -preset fast -profile:v main \
  -crf 22 -pix_fmt yuv420p -an "$WORK_DIR/video.mp4"

if [ "$INCLUDE_AUDIO" -eq 1 ]; then
  AUDIO_DURATION=$(ffprobe -v error -show_entries format=duration \
    -of default=noprint_wrappers=1:nokey=1 "$AUDIO_FILE")
  RANDOM_START=$(awk -v total="$AUDIO_DURATION" -v frames="$NUM_FRAMES" -v loops="$LOOPS" \
    'BEGIN { srand(); available=total-frames/60*loops; print (available>0 ? rand()*available : 0) }')
  ffmpeg -hide_banner -loglevel warning -stream_loop "$((LOOPS-1))" -i "$WORK_DIR/video.mp4" \
    -ss "$RANDOM_START" -stream_loop -1 -i "$AUDIO_FILE" \
    -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 128k -af volume=0.75 \
    -shortest -movflags +faststart -n "$DEST_MP4"
else
  ffmpeg -hide_banner -loglevel warning -stream_loop "$((LOOPS-1))" -i "$WORK_DIR/video.mp4" \
    -c copy -an -movflags +faststart -n "$DEST_MP4"
fi

echo "Saved $DEST_MP4"
