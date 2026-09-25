# Fall Detection System — Build Plan
**Team Lazy Lobsters** · SU-CESI Hackathon · 1.5 days

This is the *how*. The *what/why* lives in [project.md](./project.md). Decisions below are locked from search-first research — adopt existing blocks, write only the ~50 lines of rule math ourselves.

---

## 0. The Stack (locked)

| Layer | Choice | Why |
|---|---|---|
| Language | **Python 3.11 or 3.12** (fresh venv) | MediaPipe has **no 3.13 wheels** — do not use 3.13 |
| Pose | **MediaPipe Tasks `PoseLandmarker`** (`LIVE_STREAM`, `pose_landmarker_lite.task`) | 33 keypoints, CPU real-time, current API |
| Capture/overlay | **OpenCV** (`opencv-python-headless`) + MediaPipe drawing utils | webcam frames + skeleton draw |
| Rule engine | **Hand-written** (`detector.py`) | torso angle + aspect ratio + hip velocity + stillness |
| Backend/stream | **Flask-SocketIO** + MJPEG video feed | one server: pushes alerts *and* serves the room feed |
| Frontend | Static HTML + Socket.IO JS client | alert cards (room, time, snapshot) |
| Validation | **UR Fall Detection Dataset** (Kaggle mirror) | offline test without live falls |

**Gotchas pinned now:** `numpy<2`; don't let other deps bump protobuf; use `opencv-python-headless` server-side; URFD is non-commercial license (fine for demo).

**Reference repos (lift logic, don't fork):** [rhafaelc/Fall-Detection-YOLO-MediaPipe](https://github.com/rhafaelc/Fall-Detection-YOLO-MediaPipe), [majipa007/fall_detection](https://github.com/majipa007/fall_detection), [arXiv 2503.01436](https://arxiv.org/pdf/2503.01436).

---

## 1. Repo Layout

```
Lazy-Lobsters/
├── project.md
├── PLAN.md
├── requirements.txt
├── models/pose_landmarker_lite.task   # downloaded once
├── src/
│   ├── pose.py          # webcam → PoseLandmarker → 33 keypoints + draw
│   ├── features.py      # per-frame metrics (normalized by body height)
│   ├── detector.py      # state machine: fall + distress rules
│   ├── app.py           # Flask-SocketIO: MJPEG feed + alert emit
│   └── static/index.html # nurse dashboard (Socket.IO client)
└── tests/run_on_dataset.py  # validate against URFD
```

---

## 2. Per-Frame Features (`features.py`)

All normalized by **body height in pixels** (shoulder→ankle) so thresholds are camera-distance invariant.

- `centroid_y` — mean y of hips+shoulders
- `velocity_y` — Δcentroid_y / Δt (downward spike = fall trigger)
- `aspect_ratio` — bbox width ÷ height (high = lying)
- `torso_angle` — spine vs floor (≈0° horizontal = fall)
- `wrists_above_shoulders` — bool, for distress gesture
- `motion` — frame-to-frame keypoint delta (low = stillness)

## 3. State Machine (`detector.py`) — the false-positive killer

```
UPRIGHT ─velocity spike─► FALLING ─landing posture─► ON_GROUND(timer)
   │                                                      │
   │                              stillness > N sec ──────┼──► FALL ✔
   │                              arms overhead/waving ───┘──► DISTRESS ✔
   └─ slow descent (no spike) ──► SITTING (ignore)
```

Fall = **velocity spike → low+horizontal landing → stillness held N sec.** All three gates in sequence. Slow sit/bend never trips the spike gate. Distress path = conscious patient (arms overhead, MVP gesture) fires independently.

## 4. Backend (`app.py`)

- `/video_feed` → MJPEG `multipart/x-mixed-replace` stream of annotated frames
- detection loop calls `socketio.emit('alert', {room_id, timestamp, type, snapshot_b64})` on FALL/DISTRESS
- one Flask process runs capture + detection + serving

## 5. Frontend (`index.html`)

- `<img src="/video_feed">` live room view
- Socket.IO client appends an alert card (room, timestamp, type, snapshot) on `alert` event; newest on top, color-coded by type

---

## 6. Build Order (cut from the bottom if behind)

| # | Task | Owner (per project.md) | Done = |
|---|---|---|---|
| 1 | venv 3.11, `requirements.txt`, download `.task` model | Azhar | `pip install` clean |
| 2 | `pose.py` — webcam → skeleton overlay window | Azhar/Malaika | live skeleton on screen |
| 3 | `features.py` — compute 6 metrics, print live | Malaika | numbers move correctly |
| 4 | `detector.py` — state machine, tune spike/stillness thresholds | Malaika/Azhar | fall prints "FALL", sit doesn't |
| 5 | `app.py` — MJPEG feed + Socket.IO alert emit | Azhar | feed visible in browser |
| 6 | `index.html` — alert cards + live feed | Malaika | alert card pops on fall |
| 7 | Arms-overhead distress gesture | Azhar | wave → DISTRESS alert |
| 8 | Validate on URFD, log results, tune | Edouard + all | testing-plan table filled |
| — | **Stretch:** arm-waving · Signal-for-Help (MediaPipe Hands) · multi-room | — | only if ahead |

**Fallback cut order (from project.md §12):** mobile/cloud notif → acknowledge button → multi-room → persistent DB (in-memory list is fine).

---

## 7. Test Scenarios (from project.md §10)

Fall from standing · fall near bed edge → must FLAG.
Sit quickly · bend to pick up · lie down to rest → must NOT flag.
Log: date, observation, pass/partial/fail, screenshot.

## 8. requirements.txt

```
mediapipe
opencv-python-headless
flask
flask-socketio
numpy<2
```

---

### First two commands
```bash
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# then download pose_landmarker_lite.task into models/
```
