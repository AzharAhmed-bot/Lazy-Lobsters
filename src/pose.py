"""Pose extraction wrapper around MediaPipe Tasks PoseLandmarker.

Returns the 33 normalized body keypoints per frame and draws the skeleton.
Uses VIDEO running mode so it works identically on a live webcam and on a
video file (we just feed monotonic timestamps).
"""
from dataclasses import dataclass

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

# MediaPipe Pose 33-keypoint indices.
NOSE = 0
L_EYE_INNER, L_EYE, L_EYE_OUTER = 1, 2, 3
R_EYE_INNER, R_EYE, R_EYE_OUTER = 4, 5, 6
L_EAR, R_EAR = 7, 8
MOUTH_L, MOUTH_R = 9, 10
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_PINKY, R_PINKY = 17, 18
L_INDEX, R_INDEX = 19, 20
L_THUMB, R_THUMB = 21, 22
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28
L_HEEL, R_HEEL = 29, 30
L_FOOT, R_FOOT = 31, 32

# Full MediaPipe topology — face, arms (incl. hands), torso, legs, feet.
POSE_CONNECTIONS = [
    # face
    (0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8), (9, 10),
    # arms + hands
    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
    # torso
    (11, 23), (12, 24), (23, 24),
    # legs + feet
    (23, 25), (24, 26), (25, 27), (26, 28),
    (27, 29), (28, 30), (29, 31), (30, 32), (27, 31), (28, 32),
]

DRAW_VIS = 0.3   # visibility floor for drawing a joint/edge


@dataclass
class Keypoint:
    x: float  # normalized 0..1 (fraction of frame width)
    y: float  # normalized 0..1 (fraction of frame height)
    z: float
    visibility: float


class PoseModel:
    def __init__(self, model_path: str):
        base = mp_python.BaseOptions(model_asset_path=model_path)
        opts = vision.PoseLandmarkerOptions(
            base_options=base,
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.6,
            min_pose_presence_confidence=0.5,   # stops ghost poses on empty frames
            min_tracking_confidence=0.6,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(opts)

    def detect(self, frame_bgr, timestamp_ms: int):
        """Return list[Keypoint] (len 33) for the first person, or None."""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(mp_image, timestamp_ms)
        if not result.pose_landmarks:
            return None
        return [Keypoint(p.x, p.y, p.z, p.visibility) for p in result.pose_landmarks[0]]

    def close(self):
        self._landmarker.close()


def draw_skeleton(frame, kps, color=(0, 255, 0)):
    """Draw keypoints + connections onto a BGR frame in place."""
    if kps is None:
        return frame
    h, w = frame.shape[:2]
    pts = [(int(k.x * w), int(k.y * h)) for k in kps]
    for a, b in POSE_CONNECTIONS:
        if kps[a].visibility > DRAW_VIS and kps[b].visibility > DRAW_VIS:
            cv2.line(frame, pts[a], pts[b], color, 2)
    for i, k in enumerate(kps):
        if k.visibility > DRAW_VIS:
            cv2.circle(frame, pts[i], 3, (0, 0, 255), -1)
    return frame
