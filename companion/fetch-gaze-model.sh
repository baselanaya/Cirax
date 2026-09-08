#!/bin/sh
# Downloads the MobileGaze ONNX weights (MobileOne-S0, 4.8 MB, MIT license —
# https://github.com/yakhyo/gaze-estimation) next to this script so
# gaze_cam.py picks them up automatically.
set -e

DEST="$(dirname "$0")/models/gaze.onnx"
URL="https://github.com/yakhyo/gaze-estimation/releases/download/weights/mobileone_s0_gaze.onnx"

if [ -f "$DEST" ]; then
  echo "already present: $DEST"
  exit 0
fi

mkdir -p "$(dirname "$DEST")"
echo "downloading MobileGaze weights (~4.8 MB)..."
curl -fL --progress-bar -o "$DEST" "$URL"
echo "saved to $DEST"
echo "also install the runtime: pip install onnxruntime"
