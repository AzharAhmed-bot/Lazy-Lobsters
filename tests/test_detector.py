"""Synthetic tests for the fused fall/distress state machine — no camera needed.

We drive FallDetector with crafted per-frame (box, pose) cues on a controllable
clock, so we can prove the decision logic without a webcam or live falls. This is
the regression net for the multi-cue fusion: every scenario below maps to a row in
TEST_PROTOCOL.md.

Run:  pipenv run python tests/test_detector.py      (or: pipenv run pytest tests/)
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import detector as D
from detector import FallDetector, State

# ---- controllable clock (monkeypatch the detector's time source) -----------
_clock = [1000.0]
D._now = lambda: _clock[0]


def tick(dt=0.1):
    _clock[0] += dt


def box(label, motion=0.0):
    """Fake BoxFeatures: the detector only reads .stable_label and .motion."""
    return SimpleNamespace(stable_label=label, motion=motion)


def pose(vy=0.0, torso=2.0, aspect=0.45, motion=0.0, wrists_up=False,
         lw_above=False, rw_above=False, lw_x=0.0, rw_x=0.0):
    """Fake features.Features with the fields the detector reads."""
    return SimpleNamespace(velocity_y=vy, torso_angle=torso, aspect_ratio=aspect,
                           motion=motion, wrists_up=wrists_up,
                           left_wrist_above=lw_above, right_wrist_above=rw_above,
                           left_wrist_x=lw_x, right_wrist_x=rw_x)


def feed(det, b, p, frames, dt=0.1):
    """Run `frames` identical updates; return the last event seen (if any)."""
    seen = None
    for _ in range(frames):
        det.update(b, p)
        if det.last_event:
            seen = det.last_event
        tick(dt)
    return seen


def fresh():
    _clock[0] = 1000.0
    return FallDetector()


# ---- scenarios -------------------------------------------------------------
def test_standing_never_alarms():
    det = fresh()
    ev = feed(det, box("standing"), pose(vy=0.0), 20)
    assert det.fall_state == State.STANDING
    assert ev is None


def test_sitting_is_not_a_fall():
    det = fresh()
    feed(det, box("sitting"), pose(vy=0.0, torso=2.0, aspect=0.7), 10)
    assert det.fall_state == State.SITTING
    assert det.last_event is None


def test_slow_lie_down_does_not_fire():
    """Pose geometry says horizontal (lying) but there is NO velocity/impact spike."""
    det = fresh()
    feed(det, box("standing"), pose(vy=0.1), 5)                  # upright, calm
    ev = feed(det, box("fallen"), pose(vy=0.15, torso=80, aspect=2.5, motion=0.0), 20)
    assert det.fall_state == State.LYING
    assert ev is None


def test_real_fall_fires():
    """Spike (fast descent) -> fallen posture -> held still -> FALL."""
    det = fresh()
    feed(det, box("standing"), pose(vy=0.0), 3)
    det.update(box("fallen"), pose(vy=1.3, torso=85, aspect=2.6))   # the spike frame
    tick()
    ev = feed(det, box("fallen", motion=0.02), pose(vy=0.1, torso=85, aspect=2.6, motion=0.01), 15)
    assert det.fall_state == State.FALL
    assert ev == "FALL"


def test_pose_only_lying_fall_fires_when_yolo_blind():
    """The snap_005 fix: YOLO returns NO box, but pose geometry + spike still detect
    the fall and confirm it on pose-motion stillness."""
    det = fresh()
    feed(det, None, pose(vy=0.0, torso=3), 3)
    det.update(None, pose(vy=1.4, torso=57, aspect=2.86))          # spike, YOLO blind
    tick()
    ev = feed(det, None, pose(vy=0.1, torso=57, aspect=2.86, motion=0.0), 15)
    assert det.fall_state == State.FALL
    assert ev == "FALL"


def test_soft_fall_with_impact_fires():
    """A descent below the hard-velocity threshold but with a sharp impact (accel)
    still counts as a spike (recall for slumps/collapses)."""
    det = fresh()
    det.update(box("standing"), pose(vy=0.0))                      # seed velocity history
    tick()
    det.update(box("fallen"), pose(vy=0.6, torso=85, aspect=2.6))  # vy<0.9 but accel ~6
    assert det.fall_state == State.FALLING                          # impact promoted it
    tick()
    ev = feed(det, box("fallen", motion=0.02), pose(vy=0.1, torso=85, aspect=2.6, motion=0.0), 15)
    assert ev == "FALL"


def test_getup_cancels_fall():
    det = fresh()
    feed(det, box("standing"), pose(vy=0.0), 2)
    det.update(box("fallen"), pose(vy=1.3, torso=85, aspect=2.6))
    tick()
    feed(det, box("fallen", motion=0.02), pose(vy=0.1, torso=85, aspect=2.6, motion=0.0), 15)
    assert det.fall_state == State.FALL
    ev = feed(det, box("standing"), pose(vy=-0.5, torso=3, aspect=0.4), 10)  # stands back up
    assert det.fall_state == State.STANDING


def test_deep_bend_does_not_false_fall():
    """A caregiver bending deeply over a bed: torso reaches ~52deg with an impact-grade
    accel, held still — but the trunk bbox stays NARROW (aspect < 1.5), so the raised
    angle gate (60deg) must keep it out of the fall cascade. Regression for review HIGH-1."""
    det = fresh()
    det.update(box("standing"), pose(vy=0.3, torso=10, aspect=0.5))   # seed velocity
    tick()
    det.update(box("standing"), pose(vy=0.6, torso=52, aspect=0.7))   # accel spike + bend
    tick()
    ev = feed(det, box("standing", motion=0.02),
              pose(vy=0.1, torso=52, aspect=0.7, motion=0.0), 20)      # holds bent + still
    assert det.fall_state != State.FALL
    assert ev != "FALL"


def test_slow_collapse_in_lying_escalates():
    """A sub-threshold slow collapse lands in LYING (no spike). It must NOT dead-end:
    after prolonged stillness it escalates to a low-priority alert. Regression for HIGH-2."""
    det = fresh()
    feed(det, box("standing"), pose(vy=0.1), 3)
    feed(det, box("fallen"), pose(vy=0.2, torso=80, aspect=2.5, motion=0.0), 5)
    assert det.fall_state == State.LYING            # no spike -> LYING, no alert yet
    ev = feed(det, box("fallen", motion=0.02),
              pose(vy=0.0, torso=80, aspect=2.5, motion=0.0), 650, dt=0.1)  # > 60s still
    assert det.long_lie is True
    assert ev is not None and "LONG LIE" in ev


def test_lying_survives_single_frame_flicker():
    """One spurious not-fallen frame must not snap LYING back to STANDING (debounce).
    Regression for review MEDIUM-2."""
    det = fresh()
    feed(det, box("fallen"), pose(vy=0.2, torso=80, aspect=2.5, motion=0.0), 5)
    assert det.fall_state == State.LYING
    det.update(box("standing"), pose(vy=0.0, torso=5, aspect=0.5))   # single flicker frame
    assert det.fall_state == State.LYING            # still LYING — not cleared on one frame


def test_distress_arms_overhead():
    det = fresh()
    ev = feed(det, box("standing"), pose(vy=0.0, wrists_up=True), 15)
    assert det.distress is True
    assert ev is not None and "DISTRESS" in ev


def test_long_lie_escalates():
    det = fresh()
    feed(det, box("standing"), pose(vy=0.0), 2)
    det.update(box("fallen"), pose(vy=1.3, torso=85, aspect=2.6))
    tick()
    feed(det, box("fallen", motion=0.02), pose(vy=0.1, torso=85, aspect=2.6, motion=0.0), 15)
    assert det.fall_state == State.FALL
    ev = feed(det, box("fallen", motion=0.02), pose(vy=0.0, torso=85, aspect=2.6, motion=0.0),
              350, dt=0.1)   # > LONG_LIE_SECONDS of stillness
    assert det.long_lie is True
    assert ev == "LONG LIE: no recovery"


# ---- runner (works without pytest) -----------------------------------------
if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:   # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
