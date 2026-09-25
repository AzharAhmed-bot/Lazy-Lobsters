# Fall Detection — Live Test Protocol

Run `pipenv run python src/run.py --source 0 --room-id ROOM-1`, stand **~6–8 ft
from the camera with your full body in frame**, and work through the groups below.
Watch the **banner** (top-left) and the **numbers** (`vel_y`, `accel`, `motion`).
Events print to the terminal as `[frame N] *** ... ***`, and every confirmed
FALL / LONG LIE / DISTRESS also drops an annotated snapshot + JSONL record into
`alerts/` (the evidence dispatched to emergency support).

**Posture is now FUSED:** a person is treated as "on the ground" if **either**
YOLO labels them Fallen **or** the pose geometry is horizontal (torso ≥45° from
vertical, or trunk bbox wider than tall). This is the fix for YOLO missing people
lying on the floor — verify it with test #3 and #7 even when the green YOLO box
flickers or disappears.

> ⚠️ Use a mat or cushion for the real-fall actions. Don't get hurt.

For each action log: date · what you did · banner shown · pass / partial / fail · screenshot.

---

## Group A — must NOT alarm (false-positive checks)

| # | Action | Expected banner | Watch |
|---|---|---|---|
| 1 | Stand and walk side to side | `STANDING` | `vel_y` ≈ 0, fps |
| 2 | Sit down in a chair normally | `SITTING` | no FALL |
| 3 | **Lie down slowly** on the floor (controlled) | `LYING` — **no FALL** | `vel_y` / `accel` stay low ← key test |
| 4 | Bend over to tie a shoe, stand back up | stays `STANDING` | brief `vel_y` blip only |
| 5 | Sit, then lower yourself to lie on the floor in stages | `SITTING` → `LYING` | no FALL |
| 6 | Crouch / kneel to pick something up | no FALL | — |

## Group B — must alarm (true falls)

| # | Action | Expected banner | Watch |
|---|---|---|---|
| 7 | **Fall forward** onto a mat, stay still | `FALLING` → `FALL` (red) after ~1s | `vel_y` + `accel` peak |
| 8 | **Fall backward / sideways**, stay down | `FALL` | peak numbers |
| 9 | **Collapse / slump** (legs buckle, go down fast) | `FALL` | realistic ward case |
| 10 | Fall, then **immediately get up** | `FALL` may fire, then clears to `STANDING` | get-up cancel |
| 11 | Fall and **stay down ~30 s** | `FALL` → `LONG LIE: no recovery` | escalation |
| 11b | **Slow collapse** (sub-threshold), stay still ~60 s | `LYING` → `LONG LIE: no movement` | slow-collapse safety net (no spike needed) |

## Group C — distress (conscious patient)

| # | Action | Expected banner |
|---|---|---|
| 12 | Both arms straight overhead, hold ~1.5 s | `DISTRESS: arms overhead` |
| 13 | Wave one arm overhead back-and-forth | `DISTRESS: waving` |
| 14 | While on the floor (fallen), wave for help | `DISTRESS: waving` |

## Group D — edge cases

| # | Action | Expected banner |
|---|---|---|
| 15 | Walk fully out of frame | `ABSENT` (no stuck FALL) |
| 16 | Two people in frame | tracks one person (MVP limit) |
| 17 | Stand partially behind a chair / bed | does it still detect? |

---

## What to capture for tuning

The most important comparison: the **`vel_y` and `accel` peak** on a **real fall
(#7 / #9)** vs. a **deliberate slow lie-down (#3)**. The fall thresholds
(`VELOCITY_SPIKE`, `ACCEL_SPIKE` in `src/detector.py`) sit in the gap between
those two — send the numbers and we tune. (`accel` is downward-acceleration *onset*:
**positive = speeding up toward the floor** — that's the fall cue; brief floor-impact
braking shows as negative and isn't relied on at webcam frame rates.) The pose-geometry thresholds
(`POSE_LYING_ANGLE`, `POSE_ASPECT_WIDE`) were calibrated on the debug frames; if a
genuine lie-down trips a FALL, raise them or `VELOCITY_SPIKE`.

Regression net (no camera needed): `pipenv run python tests/test_detector.py`
replays the scenarios in this table against the state machine.

## Speed dials (if fps is low)

- `--pose-model models/pose_landmarker_full.task` → lighter than the heavy default,
  still far better than lite on floor poses
- `--imgsz 416` → faster YOLO, slightly less accurate
