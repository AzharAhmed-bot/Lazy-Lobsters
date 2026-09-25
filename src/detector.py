"""Hybrid fall + distress state machine with multi-cue (late) fusion.

Every signal comes from the model best suited to it, and the "on the ground"
decision is FUSED across cues so a single model's miss does not blind the system:

  - SPEED of descent   -> MediaPipe pose centroid velocity (features.py), on a real
                          measured dt. Separates a fall from a controlled lie-down.
  - IMPACT/ONSET       -> derivative of that velocity (downward acceleration). A real
                          fall RAMPS UP its downward speed sharply over one frame; a
                          slow lie-down does not. (At 20-30fps the brief floor-contact
                          deceleration is not resolvable, so we use the acceleration
                          ONSET — positive = speeding up downward — as the usable cue.)
  - POSTURE (on the ground?) -> FUSION of YOLO's debounced label (box_features.py)
                          *and* pose geometry (torso angle + trunk aspect ratio).
                          YOLOv11n alone misses people lying on the floor and
                          mislabels floor postures as "standing"; the pose geometry
                          is an independent witness that the trunk is horizontal.
  - STILLNESS          -> YOLO box IoU change (scale-invariant); falls back to pose
                          keypoint motion when YOLO has lost the box entirely.
  - DISTRESS gestures  -> MediaPipe pose (arms overhead / waving).

  FALL  = fast descent (velocity OR impact spike) + on-the-ground posture (fused)
          + held still.
  LYING = on-the-ground posture reached WITHOUT a spike (a controlled lie-down) — no alert.
  LONG LIE = confirmed FALL + prolonged immobility (the clinically dangerous case).

Why fusion: vision-only fall baselines have high false-positive AND false-negative
rates from any single cue; decision-level (late) fusion of independent cues lowers
both (see Bourke/ScienceDirect S0021929000001172, MDPI Sensors 21/3/947,
PMC10255727 on impact+stillness, and PMC12526565 on late-fusion FPR reduction).
The pose-geometry thresholds below were calibrated on the team's own debug frames:
a true lying person read torso 57deg / aspect 2.86 while every standing/sitting
frame read torso <4deg / aspect <0.85 — a clean separation.

velocity is in BODY-heights/sec (pose, distance-invariant); box motion is 1-IoU;
pose motion is mean keypoint displacement in body-scale units.
"""
from collections import deque
import time
from enum import Enum

from yolo_model import STANDING, SITTING, FALLEN

# --- Fall thresholds --------------------------------------------------------
VELOCITY_SPIKE = 0.9       # pose centroid body-heights/sec downward = "falling fast"
ACCEL_SPIKE = 4.0          # body-heights/sec^2: hard impact (corroborates a softer descent)
SOFT_VELOCITY_FRAC = 0.6   # a descent this fraction of VELOCITY_SPIKE *with* an impact counts
SPIKE_MEMORY_SECONDS = 1.2 # a spike counts toward a fall for this long after it
STILLNESS_MOTION = 0.12    # box (1-IoU) below this = still
POSE_STILLNESS_MOTION = 0.04  # pose keypoint motion (body-scale units) below this = still
STILLNESS_SECONDS = 1.0    # Fallen + still this long -> confirm FALL
GETUP_SECONDS = 0.5        # leaving Fallen this long cancels the pending/confirmed fall
LONG_LIE_SECONDS = 30.0    # confirmed FALL + still this long -> "long lie" (tune live)
LYING_ESCALATION_SECONDS = 60.0  # uncategorised LYING + still this long -> low-prio "check patient"

# --- Pose-geometry posture fusion (calibrated on debug frames) --------------
# A real lying person read torso 57deg / aspect 2.86; a deep forward BEND can reach
# ~45-55deg from vertical but keeps a tall (narrow) trunk bbox. So the angle gate is
# set ABOVE the bend range (60deg), and the genuinely-horizontal lying case that sits
# just under it (snap_005, 57deg) is still caught by the wide-aspect gate.
POSE_LYING_ANGLE = 60.0    # torso degrees-from-vertical >= this => trunk unambiguously horizontal
# Aspect gate calibrated on the debug frames: the WIDEST any upright/sitting frame
# reached was 0.84 (a slouched sit); genuine floor frames read 1.34 - 2.86. 1.2 sits
# in that empty gap, so it catches more on-the-floor cases (e.g. snap_018 @ 1.34) with
# clear margin above every upright frame. (pose_down only ALARMS when paired with a
# velocity spike or 60s stillness, so a momentary wide read can't fire a false FALL.)
POSE_ASPECT_WIDE = 1.2     # trunk bbox width/height >= this => body is flat / on the floor

# --- Distress thresholds ----------------------------------------------------
DISTRESS_SECONDS = 1.0
WAVE_WINDOW_SECONDS = 1.5
WAVE_MIN_REVERSALS = 3
WAVE_MIN_AMPLITUDE = 0.15  # body-scale units
DISTRESS_CLEAR_SECONDS = 2.0

# --- Absence (no-person) handling -------------------------------------------
ABSENCE_PENDING_SECONDS = 1.5
ABSENCE_CLEAR_SECONDS = 8.0
# ----------------------------------------------------------------------------


class State(Enum):
    STANDING = "STANDING"
    SITTING = "SITTING"
    LYING = "LYING"
    FALLING = "FALLING"
    FALL = "FALL"
    DISTRESS = "DISTRESS"
    ABSENT = "ABSENT"


def _now():
    return time.monotonic()


def _count_reversals(samples):
    if len(samples) < 3:
        return 0
    reversals = 0
    last_extreme = samples[0]
    direction = 0
    for x in samples[1:]:
        if direction >= 0 and x > last_extreme:
            last_extreme, direction = x, 1
        elif direction <= 0 and x < last_extreme:
            last_extreme, direction = x, -1
        if direction == 1 and x < last_extreme - WAVE_MIN_AMPLITUDE:
            reversals += 1
            last_extreme, direction = x, -1
        elif direction == -1 and x > last_extreme + WAVE_MIN_AMPLITUDE:
            reversals += 1
            last_extreme, direction = x, 1
    return reversals


class FallDetector:
    def __init__(self):
        self.fall_state = State.STANDING
        self.distress = False
        self.distress_reason = ""
        self.long_lie = False
        self.last_event = None
        self.accel_y = 0.0           # exposed for the overlay (impact readout)

        self._prev_vy = 0.0
        self._prev_vy_t = 0.0
        self._spike_at = 0.0
        self._fallen_since = 0.0
        self._still_since = 0.0
        self._left_fallen_at = 0.0
        self._fall_at = 0.0
        self._distress_since = 0.0
        self._distress_active_at = 0.0
        self._absent_since = 0.0
        self._wave = deque()

    @property
    def display_state(self):
        if self.fall_state == State.FALL:
            return State.FALL
        if self.distress:
            return State.DISTRESS
        return self.fall_state

    # -- distress (pose: arms overhead / waving) -----------------------------
    def _update_distress(self, p, now):
        # p is a features.Features (or None); both expose the wrist fields used here.
        if p is None:
            self._distress_since = 0.0
            self._wave.clear()
            if self.distress and now - self._distress_active_at >= DISTRESS_CLEAR_SECONDS:
                self.distress = False
            return

        held, reason = False, ""
        if p.wrists_up:
            if self._distress_since == 0.0:
                self._distress_since = now
            if now - self._distress_since >= DISTRESS_SECONDS:
                held, reason = True, "arms overhead"
        else:
            self._distress_since = 0.0

        if p.left_wrist_above:
            self._wave.append((now, p.left_wrist_x))
        elif p.right_wrist_above:
            self._wave.append((now, p.right_wrist_x))
        else:
            self._wave.clear()
        while self._wave and now - self._wave[0][0] > WAVE_WINDOW_SECONDS:
            self._wave.popleft()
        if _count_reversals([x for _, x in self._wave]) >= WAVE_MIN_REVERSALS:
            held, reason = True, "waving"

        if held:
            self._distress_active_at = now
            if not self.distress:
                self.distress = True
                self.distress_reason = reason
                self.last_event = f"DISTRESS: {reason}"
        elif self.distress and now - self._distress_active_at >= DISTRESS_CLEAR_SECONDS:
            self.distress = False

    # -- no person -----------------------------------------------------------
    def update_absent(self):
        self.last_event = None
        now = _now()
        if self._absent_since == 0.0:
            self._absent_since = now
        elapsed = now - self._absent_since
        self._wave.clear()
        self._distress_since = 0.0
        self._prev_vy_t = 0.0        # reset velocity history; no phantom impact on return
        self.accel_y = 0.0
        if self.fall_state == State.FALLING and elapsed >= ABSENCE_PENDING_SECONDS:
            self.fall_state = State.STANDING
        elif self.fall_state == State.FALL and elapsed >= ABSENCE_CLEAR_SECONDS:
            self.fall_state = State.STANDING
            self.long_lie = False
        elif self.fall_state not in (State.FALL, State.FALLING):
            self.fall_state = State.ABSENT
        if elapsed >= DISTRESS_CLEAR_SECONDS:
            self.distress = False
        return self.display_state

    # -- cue fusion helpers --------------------------------------------------
    def _impact_spike(self, pose, now):
        """Fall SIGNATURE: a fast downward pose-centroid velocity, OR a softer descent
        whose downward speed RAMPS UP sharply (high positive acceleration onset).
        accel_y = (vy - prev_vy)/dt is positive while speeding up toward the floor
        (the cue we trigger on) and negative while braking; floor-contact deceleration
        is too brief to resolve at camera frame rates. Either condition refreshes the
        spike timer. Returns True if a spike is currently 'remembered'."""
        self.accel_y = 0.0
        if pose is not None:
            if self._prev_vy_t > 0.0:
                d = now - self._prev_vy_t
                if d > 1e-3:
                    self.accel_y = (pose.velocity_y - self._prev_vy) / d
            self._prev_vy, self._prev_vy_t = pose.velocity_y, now

            hard_descent = pose.velocity_y >= VELOCITY_SPIKE
            soft_with_impact = (pose.velocity_y >= SOFT_VELOCITY_FRAC * VELOCITY_SPIKE
                                and self.accel_y >= ACCEL_SPIKE)
            if hard_descent or soft_with_impact:
                self._spike_at = now
        return now - self._spike_at <= SPIKE_MEMORY_SECONDS

    @staticmethod
    def _pose_down(pose):
        """Independent 'trunk is horizontal' witness from pose geometry — the cue
        that catches a person on the floor when YOLO misses the box or mislabels
        it 'standing'. Calibrated on debug frames (lying: 57deg/2.86; upright: <4deg/<0.85)."""
        if pose is None:
            return False
        return (pose.torso_angle >= POSE_LYING_ANGLE
                or pose.aspect_ratio >= POSE_ASPECT_WIDE)

    @staticmethod
    def _is_still(box, pose):
        """Stillness from the YOLO box (scale-invariant IoU) when present; fall back
        to pose keypoint motion when YOLO has lost the box (common once on the floor)."""
        if box is not None:
            return box.motion <= STILLNESS_MOTION
        if pose is not None:
            return pose.motion <= POSE_STILLNESS_MOTION
        return False

    # -- main update ---------------------------------------------------------
    def update(self, box, pose):
        """box: BoxFeatures or None (YOLO posture). pose: features.Features or None
        (speed + geometry + distress). Returns display_state; sets last_event on an
        alert. The 'on the ground' decision is FUSED across YOLO and pose so neither
        model's miss can silently disable fall detection."""
        self.last_event = None
        now = _now()
        self._absent_since = 0.0

        self._update_distress(pose, now)

        if box is None and pose is None:
            if self.fall_state == State.ABSENT:
                self.fall_state = State.STANDING
            return self.display_state

        recent_spike = self._impact_spike(pose, now)

        # FUSED posture: on the ground if YOLO says Fallen OR pose geometry is horizontal.
        yolo_fallen = box is not None and box.stable_label == FALLEN
        fallen = yolo_fallen or self._pose_down(pose)
        sitting = box is not None and box.stable_label == SITTING
        still = self._is_still(box, pose)

        if fallen:
            if self._fallen_since == 0.0:
                self._fallen_since = now
            self._left_fallen_at = 0.0
        elif self._fallen_since != 0.0 and self._left_fallen_at == 0.0:
            self._left_fallen_at = now

        if self.fall_state in (State.STANDING, State.SITTING, State.ABSENT):
            if fallen and recent_spike:
                self.fall_state = State.FALLING       # fast descent onto the ground
                self._still_since = 0.0
            elif fallen:
                self.fall_state = State.LYING         # slow descent: no alert (yet)
                self._still_since = 0.0
            elif sitting:
                self.fall_state = State.SITTING
            else:
                self.fall_state = State.STANDING

        elif self.fall_state == State.LYING:
            # Dedicated branch so a single not-fallen frame (YOLO flicker / brief shift)
            # can't snap us straight back to STANDING, and so a slow collapse that lands
            # in LYING without a spike still escalates instead of silently dead-ending.
            if not fallen:
                if now - self._left_fallen_at >= GETUP_SECONDS:   # debounced get-up
                    self.fall_state = State.SITTING if sitting else State.STANDING
                    self._still_since = 0.0
                    self.long_lie = False
            elif recent_spike:
                self.fall_state = State.FALLING       # a fall signature while already down
                self._still_since = 0.0
            elif still:
                if self._still_since == 0.0:
                    self._still_since = now
                elif not self.long_lie and now - self._still_since >= LYING_ESCALATION_SECONDS:
                    self.long_lie = True
                    self.last_event = "LONG LIE: no movement"
            else:
                self._still_since = 0.0

        elif self.fall_state == State.FALLING:
            if not fallen and now - self._left_fallen_at >= GETUP_SECONDS:
                self.fall_state = State.STANDING
                self._still_since = 0.0
            elif fallen and still:
                if self._still_since == 0.0:
                    self._still_since = now
                elif now - self._still_since >= STILLNESS_SECONDS:
                    self.fall_state = State.FALL
                    self.last_event = "FALL"
                    self._fall_at = now
                    self.long_lie = False
            else:
                self._still_since = 0.0

        elif self.fall_state == State.FALL:
            if not fallen and now - self._left_fallen_at >= GETUP_SECONDS:
                self.fall_state = State.STANDING
                self._fallen_since = 0.0
                self.long_lie = False
            elif (not self.long_lie and still
                  and now - self._fall_at >= LONG_LIE_SECONDS):
                self.long_lie = True
                self.last_event = "LONG LIE: no recovery"

        if not fallen:
            self._fallen_since = 0.0

        return self.display_state
