"""YOLOv11 fall-posture detector (Ultralytics).

Wraps the melihuzunoglu/human-fall-detection model, which classifies a person's
posture per frame into Standing / Sitting / Fallen and returns a bounding box.

This is the per-frame POSTURE signal. It cannot by itself tell a genuine fall
from a controlled lie-down (both end up "Fallen") — that distinction is made by
the temporal rule layer in detector.py using the box's vertical velocity.
"""
from dataclasses import dataclass

# Canonical posture labels (model class names are normalized into these).
STANDING, SITTING, FALLEN = "standing", "sitting", "fallen"


@dataclass
class Detection:
    label: str          # STANDING | SITTING | FALLEN
    conf: float
    x1: float           # bbox in pixels
    y1: float
    x2: float
    y2: float

    @property
    def cx(self):
        return (self.x1 + self.x2) / 2.0

    @property
    def cy(self):
        return (self.y1 + self.y2) / 2.0

    @property
    def w(self):
        return self.x2 - self.x1

    @property
    def h(self):
        return self.y2 - self.y1


def _normalize_label(name: str) -> str:
    n = name.strip().lower()
    if n.startswith("fall") or "down" in n or n == "lying":
        return FALLEN
    if n.startswith("sit"):
        return SITTING
    return STANDING


class YoloFallModel:
    def __init__(self, model_path: str, conf: float = 0.35, imgsz: int = 480):
        from ultralytics import YOLO   # lazy: keeps torch out of import-time
        self.model = YOLO(model_path)
        self.conf = conf
        self.imgsz = imgsz            # smaller = faster on CPU (640 default -> 480)
        # idx -> normalized label
        self.names = {i: _normalize_label(n) for i, n in self.model.names.items()}

    def detect(self, frame_bgr):
        """Return the highest-confidence Detection in the frame, or None."""
        res = self.model.predict(frame_bgr, conf=self.conf, imgsz=self.imgsz,
                                 verbose=False)[0]
        boxes = res.boxes
        if boxes is None or len(boxes) == 0:
            return None
        i = int(boxes.conf.argmax())
        cls = int(boxes.cls[i])
        x1, y1, x2, y2 = (float(v) for v in boxes.xyxy[i].tolist())
        return Detection(self.names.get(cls, STANDING), float(boxes.conf[i]),
                         x1, y1, x2, y2)
