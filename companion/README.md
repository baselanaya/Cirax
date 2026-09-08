# Cirax Camera — eye-contact correction companion

Real-time eye-contact correction for video calls: your webcam feed is
processed so your irises point toward the camera (even while you read
Cirax's answers on screen), and published as a virtual camera device that
Zoom / Meet / Teams select like any webcam.

**All processing is local.** Frames never leave the machine.

## Setup (CachyOS / Arch)

```sh
sudo pacman -S v4l2loopback-dkms python  # headers for your kernel too
sudo modprobe v4l2loopback video_nr=10 card_label="Cirax Camera" exclusive_caps=1

cd companion
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python mediapipe==0.10.14 opencv-python numpy onnxruntime
```

### Neural gaze estimation (recommended)

By default the corrector uses a geometric iris-ratio estimate. Install the
**MobileGaze** network (MobileOne-S0, 4.8 MB, MIT, trained on Gaze360) for an
estimator that is robust to glasses, lighting and eyelid shape (~7 ms/frame
on CPU):

```sh
sh fetch-gaze-model.sh   # -> models/gaze.onnx
```

`gaze_cam.py` auto-detects `models/gaze.onnx` and switches to model mode
(`--gaze-model off` forces the geometric fallback, `--gaze-model PATH`
points at other weights). In model mode the network reads the face crop and
the eye warp steers opposite to the estimated gaze angle; `--gaze-gain`
tunes how many aperture-widths are shifted per degree of gaze.

## Run

```sh
# webcam -> corrected virtual camera
env -u LD_LIBRARY_PATH .venv/bin/python gaze_cam.py \
  --input /dev/video0 --output /dev/video10 --strength 0.7

# offline test with a still image, writing a video file
env -u LD_LIBRARY_PATH .venv/bin/python gaze_cam.py \
  --input face.jpg --output out.mp4 --fps 30
```

Then pick **"Cirax Camera"** as the camera in Zoom / Meet / Teams.

## Flags

| Flag | Default | Meaning |
|---|---|---|
| `--strength` | 0.7 | correction strength 0..1 |
| `--neutral-v` | 0.47 | vertical iris ratio that reads as camera-facing (geometric mode) |
| `--gaze-model` | auto | `auto` / path to ONNX weights / `off` |
| `--gaze-gain` | 0.028 | model mode: aperture-width fraction shifted per gaze degree |
| `--frames` | ∞ | stop after N frames (testing) |
| `--preview` | off | live preview window |

## Notes & limits

- The correction shifts the eyeball content within the eye aperture, so it
  works best for **small offsets** — exactly the "reading an overlay below
  the camera" case. Large angles would need a generative model (see the
  NVIDIA Maxine Eye Contact approach) instead of the warp.
- `--frames` exists for testing; release runs stop on Ctrl-C.
- The `-u LD_LIBRARY_PATH` on the run command avoids conflicts with
  AppImage-bundled libraries when launched from odd environments.
