#!/usr/bin/env python3
"""Cirax Camera — real-time eye-contact correction companion.

Captures your webcam, estimates where your irises point relative to the
camera, and subtly warps the eye regions toward camera-facing so a video
call sees you making eye contact while you read on-screen text. The
corrected feed is published as a virtual camera (v4l2loopback on Linux).

All processing is local: frames never leave this machine.

Usage:
  python gaze_cam.py --input /dev/video0 --output /dev/video10
  python gaze_cam.py --input face.jpg --output out.mp4 --preview   # offline test
"""

from __future__ import annotations

import argparse
import collections
import os
import sys
import time

import subprocess

import cv2
import numpy as np

# MediaPipe Face Mesh (refined) landmark indexes.
IRIS_R_CENTER = 468
IRIS_L_CENTER = 473
EYE_R = {"h": (33, 133), "v": (159, 145)}   # inner/outer corner, top/bottom lid
EYE_L = {"h": (362, 263), "v": (386, 374)}

# Vertical iris ratio (0 = top lid, 1 = bottom lid) that reads as camera-facing.
NEUTRAL_V = 0.47
# Horizontal ratio between the eye corners (0..1); 0.5 = centered.
NEUTRAL_H = 0.50

MAX_SHIFT_FRACTION = 0.12   # of eye width — beyond this the warp looks uncanny
SMOOTHING_WINDOW = 6        # EMA window for gaze estimates
# Model mode: how much of the eye-aperture width to shift per degree of gaze
# angle (10 degrees off-camera ≈ a quarter aperture at strength 1.0).
GAZE_GAIN_FRACTION = 0.028


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class GazeCorrector:
    """Estimates gaze offset and renders a subtle feathered warp that moves
    the irises toward the camera-facing pose.

    Two estimators, best available wins:
      - MobileGaze ONNX (a Gaze360-trained network on the face crop) — robust
        to glasses, lighting and eyelid shape.
      - geometric fallback — iris position inside the Face-Mesh aperture.
    """

    def __init__(self, strength: float = 0.7, neutral_v: float = NEUTRAL_V,
                 gaze_model=None, gaze_gain: float = GAZE_GAIN_FRACTION):
        import mediapipe as mp

        self.strength = clamp(strength, 0.0, 1.0)
        self.neutral_v = neutral_v
        self.gaze_model = gaze_model
        self.gaze_gain = gaze_gain
        self.mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,          # adds the 10 iris landmarks
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        # Exponential moving averages of the gaze offsets (jitter smoothing).
        self._ema_h = collections.deque(maxlen=SMOOTHING_WINDOW)
        self._ema_v = collections.deque(maxlen=SMOOTHING_WINDOW)
        self._ema_yaw = collections.deque(maxlen=SMOOTHING_WINDOW)
        self._ema_pitch = collections.deque(maxlen=SMOOTHING_WINDOW)

    def _mesh_points(self, frame):
        """Runs Face Mesh; returns landmark list or None."""
        import mediapipe as mp

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = self.mesh.process(rgb)
        if not res.multi_face_landmarks:
            return None
        return res.multi_face_landmarks[0].landmark

    @staticmethod
    def _face_bbox_px(pts, w, h, margin=0.35):
        """Full-face bounding box in pixels (all 468 landmarks + margin)."""
        xs = [p.x for p in pts]
        ys = [p.y for p in pts]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        mx = (x1 - x0) * margin
        my = (y1 - y0) * margin
        return (max(0, int((x0 - mx) * w)), max(0, int((y0 - my) * h)),
                min(w, int((x1 + mx) * w)), min(h, int((y1 + my) * h)))

    def estimate_model(self, frame, pts):
        """Model-mode gaze in degrees: returns (yaw, pitch, eye_px) or None."""
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = self._face_bbox_px(pts, w, h)
        if x1 - x0 < 24 or y1 - y0 < 24:
            return None
        angles = self.gaze_model.estimate(frame[y0:y1, x0:x1])
        if angles is None:
            return None
        yaw, pitch = angles
        self._ema_yaw.append(clamp(yaw, -60.0, 60.0))
        self._ema_pitch.append(clamp(pitch, -60.0, 60.0))
        # eye width in pixels from the outer eye corners (for gain scaling)
        eye_px = abs(pts[133].x - pts[33].x) * w
        return (sum(self._ema_yaw) / len(self._ema_yaw),
                sum(self._ema_pitch) / len(self._ema_pitch),
                eye_px)

    def estimate(self, frame):
        """Geometric estimator: returns (gaze_x, gaze_y, eye_boxes) with gaze
        in -1..+1 per axis (normalized eye-unit offsets), or None when no face
        is found. eye_boxes are pixel rects (x0, y0, x1, y1) around each eye."""
        pts = self._mesh_points(frame)
        if pts is None:
            return None

        ratios_v, ratios_h, boxes = [], [], []
        eye_px = 0.0
        for eye, iris_center in ((EYE_R, IRIS_R_CENTER), (EYE_L, IRIS_L_CENTER)):
            li, ri = eye["h"]
            ti, bi = eye["v"]
            li, ri, ti, bi = pts[li], pts[ri], pts[ti], pts[bi]
            w = ri.x - li.x
            h = bi.y - ti.y
            if abs(w) < 1e-6 or abs(h) < 1e-6:
                return None
            eye_px += abs(w) * frame.shape[1]  # normalized -> pixels
            ic = pts[iris_center]
            ratios_h.append((ic.x - li.x) / w)
            ratios_v.append((ic.y - ti.y) / h)
            margin = 0.55
            boxes.append((
                int((min(li.x, ri.x, ti.x, bi.x) - margin) * frame.shape[1]),
                int((min(li.y, ri.y, ti.y, bi.y) - margin) * frame.shape[0]),
                int((max(li.x, ri.x, ti.x, bi.x) + margin) * frame.shape[1]),
                int((max(li.y, ri.y, ti.y, bi.y) + margin) * frame.shape[0]),
            ))
        eye_px /= 2.0  # average eye width in pixels

        h_ratio = sum(ratios_h) / len(ratios_h)
        v_ratio = sum(ratios_v) / len(ratios_v)
        gx = clamp((h_ratio - NEUTRAL_H) * 2.0, -1.0, 1.0)
        gy = clamp((v_ratio - self.neutral_v) * 2.0, -1.0, 1.0)

        self._ema_h.append(gx)
        self._ema_v.append(gy)
        sx = sum(self._ema_h) / len(self._ema_h)
        sy = sum(self._ema_v) / len(self._ema_v)
        return sx, sy, boxes, eye_px

    def correct(self, frame):
        """Returns the corrected frame (or the original if no face found).

        Model mode (MobileGaze ONNX): the network reads the face crop and the
        eyeball content of both eyes is shifted opposite to the gaze angle,
        lids staying put — eyes read as camera-facing even mid-glance.
        Geometric fallback: per-eye, the iris is shifted to the aperture
        center from Face-Mesh landmarks alone.
        """
        pts = self._mesh_points(frame)
        if pts is None:
            return frame
        out = frame.copy()
        h, w = frame.shape[:2]

        if self.gaze_model is not None:
            est = self.estimate_model(frame, pts)
            if est is not None:
                yaw, pitch, eye_px = est
                shift_x = clamp(-yaw * self.gaze_gain, -MAX_SHIFT_FRACTION, MAX_SHIFT_FRACTION)
                shift_y = clamp(-pitch * self.gaze_gain, -MAX_SHIFT_FRACTION, MAX_SHIFT_FRACTION)

                for eye, iris_center in ((EYE_R, IRIS_R_CENTER), (EYE_L, IRIS_L_CENTER)):
                    li, ri = eye["h"]
                    ti, bi = eye["v"]
                    li, ri, ti, bi = pts[li], pts[ri], pts[ti], pts[bi]
                    ax0 = int(min(li.x, ri.x) * w)
                    ax1 = int(max(li.x, ri.x) * w)
                    ay0 = int(min(ti.y, bi.y) * h)
                    ay1 = int(max(ti.y, bi.y) * h)
                    aw, ah = ax1 - ax0, ay1 - ay0
                    if aw < 12 or ah < 8:
                        continue
                    dx = int(round(shift_x * aw * self.strength))
                    dy = int(round(shift_y * ah * self.strength))
                    if dx == 0 and dy == 0:
                        continue
                    region = out[ay0:ay1, ax0:ax1]
                    shifted = cv2.warpAffine(region, np.float32([[1, 0, dx], [0, 1, dy]]),
                                             (aw, ah))
                    mask = np.zeros((ah, aw), np.float32)
                    cv2.ellipse(mask, (aw // 2, ah // 2),
                                (int(aw * 0.46), int(ah * 0.46)), 0, 0, 360, 1.0, -1)
                    mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=aw * 0.08)
                    m3 = mask[..., None]
                    out[ay0:ay1, ax0:ax1] = (shifted * m3 + region * (1 - m3)).astype(np.uint8)
                return out

        for eye, iris_center in ((EYE_R, IRIS_R_CENTER), (EYE_L, IRIS_L_CENTER)):
            li, ri = eye["h"]
            ti, bi = eye["v"]
            li, ri, ti, bi = pts[li], pts[ri], pts[ti], pts[bi]
            ic = pts[iris_center]

            # aperture box in pixels (corners + lids, feather margin inside)
            ax0 = int(min(li.x, ri.x) * w)
            ax1 = int(max(li.x, ri.x) * w)
            ay0 = int(min(ti.y, bi.y) * h)
            ay1 = int(max(ti.y, bi.y) * h)
            if ax1 - ax0 < 12 or ay1 - ay0 < 8:
                continue
            aw, ah = ax1 - ax0, ay1 - ay0

            # where the iris is, and where it should be (aperture center,
            # a touch above center reads as attentive)
            ix, iy = ic.x * w, ic.y * h
            tx = (ax0 + ax1) / 2.0
            ty = (ay0 + ay1) / 2.0 * 0.92
            dx = int(clamp(round(tx - ix), -int(aw * 0.28), int(aw * 0.28)) * self.strength)
            dy = int(clamp(round(ty - iy), -int(ah * 0.28), int(ah * 0.28)) * self.strength)
            if dx == 0 and dy == 0:
                continue

            # feathered aperture mask: the eyeball content shifts, lids stay
            region = out[ay0:ay1, ax0:ax1]
            shifted = cv2.warpAffine(region, np.float32([[1, 0, dx], [0, 1, dy]]),
                                     (aw, ah))
            mask = np.zeros((ah, aw), np.float32)
            cv2.ellipse(mask, (aw // 2, ah // 2),
                        (int(aw * 0.46), int(ah * 0.46)), 0, 0, 360, 1.0, -1)
            mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=aw * 0.08)
            m3 = mask[..., None]
            out[ay0:ay1, ax0:ax1] = (shifted * m3 + region * (1 - m3)).astype(np.uint8)
        return out


def open_writer(path, fps, size):
    """Returns a frame sink. v4l2 devices go through an ffmpeg stdin pipe
    (OpenCV has no V4L2 VideoWriter backend); files use cv2.VideoWriter."""
    if path.startswith("/dev/video"):
        proc = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-f", "rawvideo", "-pix_fmt", "bgr24",
             "-s", f"{size[0]}x{size[1]}", "-r", str(fps), "-i", "-",
             "-f", "v4l2", "-pix_fmt", "yuv420p", path],
            stdin=subprocess.PIPE)
        return _FFmpegSink(proc)
    writer = cv2.VideoWriter(path, cv2.CAP_FFMPEG,
                             cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    if not writer.isOpened():
        raise ValueError(f"cannot open output {path}")
    return writer


class _FFmpegSink:
    """Minimal frame sink wrapping the ffmpeg process stdin."""

    def __init__(self, proc):
        self.proc = proc

    def write(self, frame):
        try:
            self.proc.stdin.write(frame.tobytes())
        except OSError:
            pass

    def release(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Cirax eye-contact camera daemon")
    ap.add_argument("--input", default="/dev/video0",
                    help="webcam device, video file, or image file to use as source")
    ap.add_argument("--output", default="/dev/video10",
                    help="virtual camera device or media file to write")
    ap.add_argument("--strength", type=float, default=0.7,
                    help="correction strength 0..1 (default 0.7)")
    ap.add_argument("--neutral-v", type=float, default=NEUTRAL_V,
                    help="vertical iris ratio that reads as camera-facing (geometric mode)")
    ap.add_argument("--gaze-model", default="auto",
                    help="MobileGaze ONNX weights: path, 'auto' (search default "
                         "locations), or 'off' for the geometric estimator")
    ap.add_argument("--gaze-gain", type=float, default=GAZE_GAIN_FRACTION,
                    help="model mode: aperture-width fraction to shift per gaze degree")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--preview", action="store_true",
                    help="show a live preview window")
    ap.add_argument("--frames", type=int, default=0,
                    help="stop after N frames (0 = run until stopped)")
    args = ap.parse_args()

    is_image = args.input.lower().endswith((".jpg", ".jpeg", ".png"))
    if is_image:
        src_frame = cv2.imread(args.input)
        if src_frame is None:
            print(f"error: cannot read input image {args.input}", file=sys.stderr)
            return 1
    else:
        cap = cv2.VideoCapture(
            args.input, cv2.CAP_V4L2 if args.input.startswith("/dev/video") else cv2.CAP_ANY)
        if args.input.startswith("/dev/video"):
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, args.fps)
        if not cap.isOpened():
            print(f"error: cannot open input {args.input}", file=sys.stderr)
            return 1

    gaze_path = None
    if args.gaze_model != "off":
        from gaze_model import MobileGaze, find_model
        gaze_path = find_model(args.gaze_model)
        if gaze_path:
            try:
                gaze = MobileGaze(gaze_path)
                print(f"gaze model: {os.path.basename(gaze_path)} "
                      f"(ONNX, input {gaze.input_hw[0]}x{gaze.input_hw[1]})")
            except Exception as exc:
                print(f"warning: gaze model failed to load ({exc}); "
                      "using the geometric estimator", file=sys.stderr)
                gaze = None
        else:
            print("gaze model not found — run companion/fetch-gaze-model.sh "
                  "for the neural estimator; using geometric fallback")
    else:
        gaze = None

    corrector = GazeCorrector(strength=args.strength, neutral_v=args.neutral_v,
                              gaze_model=gaze, gaze_gain=args.gaze_gain)

    def read_frame():
        """Yield frames from the configured source."""
        if is_image:
            while True:
                yield src_frame
        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop video files
                ret, frame = cap.read()
                if not ret:
                    return
            yield frame

    # Probe the first frame to size the writer.
    try:
        first = next(read_frame())
    except StopIteration:
        print("error: input produced no frames", file=sys.stderr)
        return 1

    try:
        writer = open_writer(args.output, args.fps,
                             (first.shape[1], first.shape[0]))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"cirax camera running: {args.input} -> {args.output} "
          f"(strength {args.strength}, {args.fps} fps). Ctrl-C to stop.")

    preview = args.preview
    try:
        frame = first
        n_written = 0
        max_frames = args.frames if args.frames > 0 else 0
        while True:
            corrected = corrector.correct(frame)
            writer.write(corrected)
            n_written += 1
            if max_frames and n_written >= max_frames:
                break
            if preview:
                cv2.imshow("cirax camera preview", corrected)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            if is_image:
                time.sleep(1 / args.fps)
            else:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = cap.read()
                    if not ret:
                        break
    except KeyboardInterrupt:
        pass

    writer.release()
    if preview:
        cv2.destroyAllWindows()
    print("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
