"""Posture features from the YOLO detection.

YOLO's job in the hybrid is the POSTURE CLASS (standing/sitting/fallen) — the
thing it was trained on and is good at. It is NOT used for kinematics: the YOLO
box center/size is unstable across posture changes, so deriving fall *speed* from
it produced false spikes. Speed comes from MediaPipe pose instead (features.py).

Here we only:
  - debounce the label (majority over a short window) to kill frame-to-frame flicker
  - measure stillness as box IoU change (scale-invariant, unlike center+size deltas)
"""
from collections import deque
from dataclasses import dataclass


@dataclass
class BoxFeatures:
    label: str          # raw label this frame
    stable_label: str   # debounced (majority of recent frames)
    conf: float
    cy: float           # box center y, normalized 0..1 (display only)
    aspect: float       # box w/h (display only)
    scale: float        # box height px (display only)
    motion: float       # smoothed (1 - IoU): 0 = perfectly still, 1 = moved off
    bbox: tuple         # (x1,y1,x2,y2) px


def _iou(a, b):
    ix1, iy1 = max(a.x1, b.x1), max(a.y1, b.y1)
    ix2, iy2 = min(a.x2, b.x2), min(a.y2, b.y2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


def _majority(labels):
    return max(set(labels), key=labels.count) if labels else None


class BoxTracker:
    """Per-frame Detection -> BoxFeatures, holding a label-debounce window."""

    def __init__(self, debounce=5):
        self._labels = deque(maxlen=debounce)
        self._prev = None

    def update(self, det, w, h):
        if det is None:
            self._labels.clear()
            self._prev = None
            return None
        motion = 1.0 - _iou(self._prev, det) if self._prev is not None else 0.0
        self._labels.append(det.label)
        stable = _majority(self._labels)
        self._prev = det
        return BoxFeatures(det.label, stable, det.conf, det.cy / h,
                           det.w / max(det.h, 1.0), det.h, motion,
                           (det.x1, det.y1, det.x2, det.y2))
