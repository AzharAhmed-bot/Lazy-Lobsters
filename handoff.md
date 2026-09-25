# Handoff — Fall Detection Build (resume here)

**Last session date:** 2026-06-18
**Where we are:** Detection logic upgraded from YOLO-gated to **multi-cue fusion**, pose
model defaulted to **heavy**, and a **fall-alert pipeline** (snapshot + JSONL +
dispatch stub) added. 9/9 synthetic detector tests pass. Env is unblocked
(`libgles2` installed, mediapipe + heavy pose load OK). Ready for live webcam tuning.

### 2026-06-18 changes (this session)
- **`detector.py` — late fusion.** "On the ground" is now `YOLO Fallen OR pose
  geometry horizontal` (torso ≥45° **or** trunk aspect ≥1.5), calibrated on the debug
  frames (real lying frame read torso 57°/aspect 2.86; all standing/sitting <4°/<0.85).
  Fixes YOLOv11n missing people on the floor (snap_005) and mislabelling them "standing"
  (snap_018). Added an **impact/acceleration** spike (catches soft slumps below the
  velocity threshold) and a **pose-motion stillness fallback** for when YOLO loses the box.
- **`alerts.py` (new).** On FALL/LONG LIE/DISTRESS: save annotated snapshot → `alerts/`,
  append a JSONL audit record (room, ISO time, type, path), dispatch to emergency
  support (logs; POSTs to `--webhook`/`ALERT_WEBHOOK` if set). Per-type 15s cooldown.
- **`run.py`.** Pose default → heavy; overlay shows `accel`; `--room-id/--alerts-dir/--webhook`.
- **`tests/test_detector.py` (new).** Camera-free regression net, 9 scenarios.

---
**Original (2026-06-17) notes below — env setup, now done.**

**Where we are (then):** Vision model is fully written. Webcam is attached. Two install steps remain before the first live test — both are the USER's to run (env setup is done by hand, not by Claude).

---

## TL;DR for next session
> "Read handoff.md. The vision model code is done and the webcam is attached. I just need to (1) `sudo apt install libgles2`, (2) set up the pipenv env with mediapipe, then run `pipenv run python src/run.py --source 0`. Model only — no UI yet."

---

## ⚙️ Environment rules (IMPORTANT)
- **Use `pipenv`, NOT the old `./venv`.** The `./venv` from the first session is abandoned.
- **The user does all installs by hand.** Claude only reports which packages/libs are missing — it does NOT run installs (no sudo password, and the user manages the env).
- **Python 3.12** for the pipenv env — MediaPipe has **no 3.13 wheels**, and the system default `python3` is 3.10 (also fine for mediapipe but we standardize on 3.12).
- **Focus right now is the MODEL ONLY.** Do NOT build the API/dashboard/UI yet — the user asked for the vision model + webcam test first. (A draft `app.py` was written then removed at the user's request.)

---

## ✅ Done

- **Stack decided** (see PLAN.md): Python 3.12, MediaPipe Tasks PoseLandmarker (VIDEO mode), OpenCV, hand-written rule engine. Flask-SocketIO + dashboard come LATER.
- **Model downloaded:** `models/pose_landmarker_lite.task` (5.6 MB).
- **Vision code written** (all in `src/`):
  - `pose.py` — MediaPipe PoseLandmarker wrapper (33 keypoints, VIDEO mode), skeleton drawing.
  - `features.py` — per-frame metrics: centroid_y, velocity_y, torso_angle, aspect_ratio, wrists_up, motion (normalized by body scale).
  - `detector.py` — fall + distress STATE MACHINE with tunable thresholds at top. Fall = velocity spike → low/horizontal landing → stillness held. Distress = arms overhead held 1s.
  - `run.py` — standalone test harness: webcam OR video file, draws skeleton + live metrics + state banner, optional `--save` to mp4.
- **Webcam attached:** `/dev/video0` and `/dev/video1` present in WSL (usbipd attach succeeded). HP True Vision 5MP, busid 1-9.

## ⛔ Blocked / TODO before first test (USER runs these)

### 1. Install OpenGL lib (the hard blocker — MediaPipe won't load: `libGLESv2.so.2` error)
Only `libgles2` is missing (libegl1/libgl1/libglib2.0-0 already present):
```bash
sudo apt-get update && sudo apt-get install -y libgles2
```

### 2. Set up pipenv env + packages
A fresh pipenv env won't see the system's opencv/numpy, so install all three into it.
Missing pip package: **mediapipe** (opencv-python + numpy<2 also installed into the clean env).
```bash
cd /home/azhar/Lazy-Lobsters
pipenv --python 3.12
pipenv install mediapipe opencv-python "numpy<2"
```

### 3. Smoke test (confirms libgles2 worked + MediaPipe loads)
```bash
pipenv run python -c "import sys; sys.path.insert(0,'src'); from pose import PoseModel; PoseModel('models/pose_landmarker_lite.task'); print('MODEL LOADS OK')"
```

### 4. Live webcam test
```bash
pipenv run python src/run.py --source 0                 # webcam, live window
# OR a video clip:
pipenv run python src/run.py --source samples/clip.mp4 --save out.mp4
# headless (no window, e.g. UR Fall Dataset clips):
pipenv run python src/run.py --source clip.mp4 --save out.mp4 --no-display
```
Watch the on-screen metrics; tune thresholds at the top of `src/detector.py` so real falls fire FALL and sitting/bending/lying don't.

## ▶️ After the model works (next phases, per PLAN.md) — NOT YET
1. **API** — `src/app.py`: Flask-SocketIO, MJPEG `/video_feed`, emit `{room_id, timestamp, type, snapshot_b64}` on event. (flask + flask-socketio are in requirements.txt; will need installing in the pipenv env when we get there.)
2. **Dashboard** — `src/static/index.html`: Socket.IO client, alert cards.
3. **Other alerts / stretch** — arm-waving gesture, Signal-for-Help (MediaPipe Hands), multi-room.

## Notes / gotchas
- WSL2 has no webcam until `usbipd attach --wsl --busid 1-9` is re-run each boot/replug (PowerShell as Admin).
- Kept full `opencv-python` (not headless) so `cv2.imshow` works for local testing.
- `numpy<2` pinned (protobuf/ABI safety). Don't let deps bump it.
- Thresholds in `detector.py` are first-guess — expect to tune them during testing.
- `current packages in system python3 (3.10): opencv 4.11.0.86, numpy 1.26.4 present; mediapipe missing` — but the pipenv (3.12) env is separate, so install fresh there.
