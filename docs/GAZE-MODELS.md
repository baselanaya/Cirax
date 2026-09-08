# Gaze estimation models — options for Cirax

*Research pass 2026-09-08. Goal: replace the geometric MediaPipe face-mesh
gaze signal (which only gives a coarse iris-within-aperture ratio) with a
learned appearance-based gaze estimator, for (a) better eye-contact
correction in the companion camera and (b) future gaze-as-input features.*

> **Status: MobileGaze is integrated** (v0.2.0). `companion/gaze_model.py`
> wraps the MobileOne-S0 ONNX export (`sh companion/fetch-gaze-model.sh`,
> ~4.8 MB); `gaze_cam.py` crops the face via MediaPipe, runs the network
> (~7 ms/frame CPU), and steers the eye warp by the estimated yaw/pitch.
> The geometric estimator remains as the fallback (`--gaze-model off`).

## What we have today

`companion/gaze_cam.py` uses MediaPipe Face Mesh (refined, 478 landmarks)
and computes iris-to-lid ratios geometrically. It works but is weak: no
head-pose compensation, no personalization, and the aperture-warp correction
is only driven by that coarse ratio. **We keep MediaPipe for face detection
and cropping either way** — the question is what estimates the gaze vector.

## Candidates

### 1. MobileGaze — `yakhyo/gaze-estimation` ⭐ recommended first

- **License:** MIT ✅ (208 ⭐, active — pushed 2026-02)
- **What:** ResNet / MobileNet-v2 / MobileOne pre-trained for gaze
  estimation (classification + regression variants), ETH-XGaze trained.
- **Why it fits:** lightweight by design → real-time on CPU, trivially
  exportable to **ONNX** and runnable via onnxruntime in a small sidecar or
  even the Electron renderer (WASM). MIT license = zero friction to bundle.
- **Accuracy:** benchmark-level for ETH-XGaze-style data; expect ~4–5°
  cross-domain — plenty for region-level context and warp steering.
- **Integration:** ONNX model file + eye-patch crop from MediaPipe +
  onnxruntime session. ~1 day of work.

### 2. GazeFollower — `GanchengZhu/GazeFollower`

- **License:** ⚠️ custom (NOASSERTION) — review before bundling
- **What:** complete webcam gaze-tracking **system**: deep-learning gaze +
  calibration + screen-coordinate mapping + recording. ACM-published with
  **1.11 cm on-screen accuracy, 0.11 cm precision**.
- **Why it fits:** it solves the hard part we haven't built — the
  calibration-to-screen-coordinate mapping — as a ready library.
- **Risk:** the custom license and Python-native stack (no ONNX); treat as
  an optional dependency or study its calibration approach.

### 3. UniGaze — `ut-vision/UniGaze` (WACV 2026) ⭐ accuracy ceiling

- **License:** ⚠️ NOASSERTION (research code; check before shipping)
- **What:** ViT + MAE large-scale pre-training on 5 gaze datasets; UniGaze-H
  beats prior SOTA across benchmarks. Weights are released ✅.
- **Why it fits:** the current accuracy ceiling for appearance-based gaze,
  strong cross-dataset generalization (i.e., robust to *your* face/lighting
  without per-user training).
- **Risk:** ViT-scale model — real-time needs a GPU; heavy for an always-on
  companion. Best as the accuracy reference or an optional "high precision"
  path.

### 4. GazeSymCAT / GazeCapsNet (2025 papers)

SOTA claims on ETH-XGaze (transformer + capsule variants). Research-grade,
no clearly packaged weights for inference — monitor, don't build on yet.

### 5. MediaPipe Iris (current) — keep as the detector layer

Not replaced: still the fastest, most robust **face + eye-region detector**
across platforms. The learned model sits on top of its eye crops.

## Recommendation

**Two-stage pipeline:** MediaPipe detects + crops the eye patches →
**MobileGaze (ONNX)** estimates the 3D gaze vector per frame → Kalman
smoothing → drives (a) the aperture-warp correction in the companion camera
and (b) future screen-region mapping. GazeFollower's calibration approach is
the reference if/when we need screen points; UniGaze is the accuracy ceiling
if we ever need offline precision.

## Sources

- [MobileGaze — yakhyo/gaze-estimation](https://github.com/yakhyo/gaze-estimation)
- [GazeFollower — ACM (2025)](https://dl.acm.org/doi/10.1145/3729410)
- [UniGaze — ut-vision/UniGaze](https://github.com/ut-vision/UniGaze) ·
  [arXiv 2502.02307](https://arxiv.org/html/2502.02307v2) · WACV 2026
- [GazeHub benchmark hub (BUAA)](https://phi-ai.buaa.edu.cn/Gazehub/)
- [AGE survey (arXiv 2104.12668)](https://www.alphaxiv.org/abs/2104.12668)
- [2025 webcam gaze paper (2.4° accuracy)](https://www.researchgate.net/publication/394721765_Real-time_Appearance-based_Gaze_Estimation_via_Web-Camera)
