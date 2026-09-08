#!/usr/bin/env python3
"""MobileGaze ONNX gaze estimator (MIT-licensed weights by yakhyo/gaze-estimation).

Runs an L2CS-style gaze network (default: MobileOne-S0, 4.8 MB) on a face
crop and returns gaze angles in degrees relative to the camera:
  yaw   = horizontal (+right), pitch = vertical (+down)

The ONNX models expose two logit tensors (yaw, pitch), each over 90 bins of
4 degrees with a 180-degree offset. The angle is the softmax expected value:
  angle_deg = sum(prob * bin_index) * 4 - 180

Optional dependency: onnxruntime (`pip install onnxruntime`). When the model
file or the runtime is missing, gaze_cam.py falls back to the geometric
iris-ratio estimator.
"""

from __future__ import annotations

import os

import cv2
import numpy as np

# Bin configuration shared by every MobileGaze/L2CS Gaze360 export.
BINS = 90
BIN_WIDTH = 4.0
ANGLE_OFFSET = 180.0
# ImageNet stats used at training time.
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

DEFAULT_MODEL_NAME = "gaze.onnx"


def model_search_paths():
    """Where fetch-gaze-model.sh (or the user) may have put the weights."""
    here = os.path.dirname(os.path.abspath(__file__))
    return [
        os.path.join(here, "models", DEFAULT_MODEL_NAME),
        os.path.expanduser(os.path.join("~", ".local", "share", "cirax", "models", DEFAULT_MODEL_NAME)),
    ]


def find_model(explicit=None):
    """Returns the first existing model path, or None."""
    if explicit and explicit != "auto":
        return explicit if os.path.isfile(explicit) else None
    for p in model_search_paths():
        if os.path.isfile(p):
            return p
    return None


def _softmax(x):
    e = np.exp(x - np.max(x, axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def _decode(logits):
    """Logits (1, 90) -> angle in degrees."""
    idx = np.arange(BINS, dtype=np.float32)
    return float((_softmax(logits)[0] * idx).sum() * BIN_WIDTH - ANGLE_OFFSET)


class MobileGaze:
    """Thin ONNX wrapper. Usage: angles = model.estimate(face_crop_bgr)."""

    def __init__(self, onnx_path):
        import onnxruntime as ort

        self.path = onnx_path
        self.session = ort.InferenceSession(
            str(onnx_path), providers=["CPUExecutionProvider"])
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        shape = inp.shape  # e.g. [1, 3, 224, 224] or dynamic strings
        try:
            self.input_hw = (int(shape[2]), int(shape[3]))
        except (TypeError, ValueError, IndexError):
            self.input_hw = (224, 224)
        names = [o.name for o in self.session.get_outputs()]
        if len(names) != 2:
            raise ValueError(f"expected 2 output nodes (yaw, pitch), got {names}")
        # Documented order: outputs[0] = yaw, outputs[1] = pitch.
        self._out_names = names

    def estimate(self, face_bgr):
        """face_bgr: full-face crop (BGR). Returns (yaw_deg, pitch_deg) or None."""
        if face_bgr is None or face_bgr.size == 0:
            return None
        rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (self.input_hw[1], self.input_hw[0]))
        x = resized.astype(np.float32) / 255.0
        x = (x - MEAN) / STD
        x = x.transpose(2, 0, 1)[None]  # HWC -> 1CHW
        outs = self.session.run(self._out_names, {self.input_name: x})
        yaw_deg = _decode(outs[0])
        pitch_deg = _decode(outs[1])
        return yaw_deg, pitch_deg
