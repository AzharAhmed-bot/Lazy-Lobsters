"""Per-frame motion/posture features derived from the 33 keypoints.

Geometry (angles, bbox) is computed in pixel space (normalized coords scaled by
frame w/h). Crucially, *velocity* and *motion* are normalized by the patient's
own BODY HEIGHT in pixels (shoulder-center -> ankle-center), not by the frame,
so thresholds are camera-distance invariant: the same physical fall produces the
same velocity_y whether the patient is near or far from the camera.

NOTE on torso_angle convention: it is degrees FROM VERTICAL — ~0 deg when the
patient is upright, ~90 deg when lying down. (Earlier docs said the opposite;
the code below is the source of truth.)
"""
import math
from dataclasses import dataclass

from pose import (NOSE, L_SHOULDER, R_SHOULDER, L_HIP, R_HIP, L_ANKLE, R_ANKLE,
                  L_WRIST, R_WRIST)

VIS = 0.3                     # per-keypoint visibility floor for geometry
CORE_VIS_MIN = 0.5            # mean core-landmark visibility below this = no reliable pose
BODY_SCALE_FLOOR = 0.15       # body_scale clamped to >= this fraction of frame height


@dataclass
class Features:
    centroid_y: float        # 0 (top) .. 1 (bottom of frame)
    velocity_y: float        # downward speed of torso centroid, BODY-heights/sec
    torso_angle: float       # degrees from vertical: ~0 upright, ~90 lying
    aspect_ratio: float      # torso bbox width / height: <1 tall, >1 wide/lying
    wrists_up: bool          # both wrists above both shoulders (arms-overhead)
    motion: float            # mean keypoint displacement vs last frame, body-scale units
    body_scale: float        # shoulder->ankle length in px (clamped); the normalizer
    core_visibility: float   # mean visibility of shoulders+hips (pose-reliability)
    # Per-wrist data for the arm-waving detector (x in body-scale units):
    left_wrist_above: bool
    right_wrist_above: bool
    left_wrist_x: float
    right_wrist_x: float


def _mid(a, b):
    return ((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)


def compute(kps, w, h, prev_kps, cy_history, dt, gap):
    """Compute one Features sample.

    kps:         list[Keypoint] (len 33) or None.
    cy_history:  caller-owned deque(maxlen>=3) of recent centroid_y; this fn appends.
    gap:         number of consecutive missed-detection frames immediately before
                 this one (0 = continuous). Non-zero => this is a re-acquisition, so
                 velocity/motion are zeroed and history reset to avoid spurious spikes.

    Returns Features, or None if there is no reliable pose (caller treats as absence).
    """
    if kps is None:
        return None

    sh = _mid(kps[L_SHOULDER], kps[R_SHOULDER])   # shoulder center (normalized)
    hp = _mid(kps[L_HIP], kps[R_HIP])             # hip center

    # Pose-reliability gate: a flimsy detection of an empty room / furniture has
    # low visibility on the core trunk landmarks. Reject it as "no pose".
    core_vis = sum(kps[i].visibility for i in (L_SHOULDER, R_SHOULDER, L_HIP, R_HIP)) / 4.0
    if core_vis < CORE_VIS_MIN:
        return None

    # Body scale = shoulder-center -> ankle-center in px (fallback: torso x2).
    ankles = [kps[i] for i in (L_ANKLE, R_ANKLE) if kps[i].visibility > VIS]
    if ankles:
        ak = (sum(a.x for a in ankles) / len(ankles), sum(a.y for a in ankles) / len(ankles))
        body_scale = math.hypot((ak[0] - sh[0]) * w, (ak[1] - sh[1]) * h)
    else:
        body_scale = math.hypot((hp[0] - sh[0]) * w, (hp[1] - sh[1]) * h) * 2.0
    body_scale = max(body_scale, BODY_SCALE_FLOOR * h)   # clamp so it can't blow up ratios

    # Torso centroid (normalized y, 0..1).
    centroid_y = (sh[1] + hp[1]) / 2.0

    # Re-acquisition: drop stale history so we don't measure a phantom jump.
    if gap > 0:
        cy_history.clear()

    # Vertical velocity in BODY-heights/sec, over the centroid history span (smoothing).
    velocity_y = 0.0
    if gap == 0 and len(cy_history) >= 2 and dt > 0:
        span = len(cy_history) - 1
        d_norm = centroid_y - cy_history[0]            # normalized frame fraction
        velocity_y = (d_norm * h) / body_scale / (span * dt)
    cy_history.append(centroid_y)

    # Torso angle from vertical (0 upright, 90 lying).
    dx = (hp[0] - sh[0]) * w
    dy = (hp[1] - sh[1]) * h
    length = math.hypot(dx, dy) or 1e-6
    torso_angle = math.degrees(math.acos(min(1.0, abs(dy) / length)))

    # Aspect ratio from TORSO+HEAD only (nose, shoulders, hips) — excludes arms so a
    # raised-arm wave doesn't read as a wide/horizontal body.
    trunk = [kps[i] for i in (NOSE, L_SHOULDER, R_SHOULDER, L_HIP, R_HIP)
             if kps[i].visibility > VIS]
    if trunk:
        xs = [k.x * w for k in trunk]
        ys = [k.y * h for k in trunk]
        bw = (max(xs) - min(xs)) or 1.0
        bh = (max(ys) - min(ys)) or 1e-6
        aspect_ratio = bw / bh
    else:
        aspect_ratio = 0.0

    # Arms-overhead (both wrists above both shoulders; smaller y = higher).
    lw, rw = kps[L_WRIST], kps[R_WRIST]
    left_wrist_above = lw.visibility > VIS and lw.y < kps[L_SHOULDER].y
    right_wrist_above = rw.visibility > VIS and rw.y < kps[R_SHOULDER].y
    wrists_up = left_wrist_above and right_wrist_above
    # Wrist x in body-scale units (for the waving amplitude/reversal test).
    left_wrist_x = (lw.x * w) / body_scale
    right_wrist_x = (rw.x * w) / body_scale

    # Motion = mean keypoint displacement since last frame, in body-scale units.
    motion = 0.0
    if gap == 0 and prev_kps is not None:
        deltas = [math.hypot((k.x - p.x) * w, (k.y - p.y) * h) / body_scale
                  for k, p in zip(kps, prev_kps)
                  if k.visibility > VIS and p.visibility > VIS]
        motion = sum(deltas) / len(deltas) if deltas else 0.0

    return Features(centroid_y, velocity_y, torso_angle, aspect_ratio, wrists_up,
                    motion, body_scale, core_vis,
                    left_wrist_above, right_wrist_above, left_wrist_x, right_wrist_x)


@dataclass
class Distress:
    wrists_up: bool          # both wrists above both shoulders (arms-overhead)
    left_wrist_above: bool
    right_wrist_above: bool
    left_wrist_x: float      # body-scale units (for waving amplitude/reversals)
    right_wrist_x: float


def distress_compute(kps, w, h):
    """Lightweight pose-only distress features (arms-overhead + per-wrist x for
    waving). Used in the hybrid pipeline where YOLO handles falls and MediaPipe
    only supplies distress gestures. Returns Distress or None."""
    if kps is None:
        return None
    sh = _mid(kps[L_SHOULDER], kps[R_SHOULDER])
    hp = _mid(kps[L_HIP], kps[R_HIP])
    if (kps[L_SHOULDER].visibility + kps[R_SHOULDER].visibility) / 2.0 < VIS:
        return None
    body_scale = max(math.hypot((hp[0] - sh[0]) * w, (hp[1] - sh[1]) * h) * 2.0,
                     BODY_SCALE_FLOOR * h)
    lw, rw = kps[L_WRIST], kps[R_WRIST]
    left_above = lw.visibility > VIS and lw.y < kps[L_SHOULDER].y
    right_above = rw.visibility > VIS and rw.y < kps[R_SHOULDER].y
    return Distress(left_above and right_above, left_above, right_above,
                    (lw.x * w) / body_scale, (rw.x * w) / body_scale)
