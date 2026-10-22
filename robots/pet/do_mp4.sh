#!/bin/bash
{
  echo "Rendering $1..."
  mkdir -p gif
  cd gif
  NUM_FRAMES=${3:-144}
  VIDEO_DURATION=$(echo "scale=2; $NUM_FRAMES / 60" | bc)
  NUM_THREADS=20
  INCLUDE_AUDIO=${4:-0} # Default: 0 (skip audio), set to 1 to include audio

  for i in $(seq 1 $NUM_THREADS); do
    openscad -q \
      --animate $NUM_FRAMES --animate_sharding $i/$NUM_THREADS \
      --imgsize 1920,1920 --colorscheme Starnight --camera $2 \
      ../$1 &
  done
  wait

  FILENAME=$(basename -- "$1")
  DEST_MP4=../devlog/$FILENAME.`date +%Y%m%d%H%M%S`.mp4

  # Concatenate PNGs into a video (single loop)
  ffmpeg -framerate 60 -pattern_type glob -i "*.png" \
    -vf "yadif,format=yuv420p" -r 60 \
    -c:v libx264 -preset fast -profile:v main -level 4.0 -crf 22 \
    -x264-params "keyint=100:weightp=1:vbv-bufsize=25000:vbv-maxrate=20000" \
    -an -y temp_video.mp4

  # Loop the video 4 times
  ffmpeg -stream_loop 3 -i temp_video.mp4 -c copy -y temp_video_looped.mp4

  if [ "$INCLUDE_AUDIO" -eq 1 ]; then
    AUDIO_DURATION=$(ffprobe -v error -show_entries format=duration \
      -of default=noprint_wrappers=1:nokey=1 ../dnb2.mp3)
    # The audio should be 4x longer to start with
    MAX_START=$(echo "scale=2; $AUDIO_DURATION - ($VIDEO_DURATION * 4)" | bc)
    RANDOM_START=$(echo "scale=2; $RANDOM % ${MAX_START%.*}" | bc)
    TEMP_AUDIO="../temp_audio_${RANDOM}.mp3"
    ffmpeg -ss $RANDOM_START -t $(echo "$VIDEO_DURATION * 4" | bc) \
      -i ../dnb2.mp3 -af "volume=0.75" "$TEMP_AUDIO" -y

    # Combine looped video and extended audio
    ffmpeg -i temp_video_looped.mp4 -i "$TEMP_AUDIO" \
      -c:v copy -c:a aac -b:a 128k -shortest "$DEST_MP4"

    # Cleanup
    rm "$TEMP_AUDIO"
  else
    # No audio, final output
    ffmpeg -i temp_video_looped.mp4 -c:v copy -an "$DEST_MP4"
  fi

  rm temp_video.mp4 temp_video_looped.mp4
  cd ..
  rm -rf gif
} && prowl "MP4" "SUCCESS" \
  || prowl "MP4" "ERROR!"
