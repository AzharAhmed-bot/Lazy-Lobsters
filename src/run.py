"""Standalone vision test harness — hybrid fall + distress detection.

Posture: YOLOv11 (models/best.pt). Speed + distress: MediaPipe pose.
The fall SPEED (slow lie-down vs fast fall) is measured from the pose centroid
velocity on a REAL measured dt — not the camera's nominal fps, and not the
unstable YOLO box.

Webcam:
    python src/run.py --source 0
Video file, saving an annotated copy:
    python src/run.py --source samples/fall.mp4 --save out.mp4
Faster (smaller YOLO input):
    python src/run.py --source 0 --imgsz 416

Keys: q = quit.
"""
import argparse
import os
import sys
import time
from collections import deque

import cv2

sys.path.insert(0, os.path.dirname(__file__))
from yolo_model import YoloFallModel, FALLEN, SITTING          # noqa: E402
from box_features import BoxTracker                             # noqa: E402
import features as feat                                         # noqa: E402
from detector import FallDetector, State                        # noqa: E402
from alerter import Esp32Alerter                                 # noqa: E402
from api_server import StatusServer                              # noqa: E402
from alerts import AlertSink                                    # noqa: E402

BANNER_COLORS = {
    State.STANDING: (0, 180, 0),
    State.SITTING: (0, 180, 0),
    State.LYING: (0, 165, 255),
    State.FALLING: (0, 165, 255),
    State.FALL: (0, 0, 255),
    State.DISTRESS: (255, 0, 255),
    State.ABSENT: (120, 120, 120),
}
BOX_COLORS = {FALLEN: (0, 0, 255), SITTING: (0, 200, 255)}


def draw_box(frame, b):
    if b is None:
        return
    x1, y1, x2, y2 = (int(v) for v in b.bbox)
    color = BOX_COLORS.get(b.stable_label, (0, 220, 0))
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.putText(frame, f"{b.stable_label} {b.conf:.2f}", (x1, max(y1 - 8, 14)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


def draw_overlay(frame, b, vel_y, accel_y, state, event, fps, distress_reason):
    h, w = frame.shape[:2]
    color = BANNER_COLORS.get(state, (200, 200, 200))
    cv2.rectangle(frame, (0, 0), (w, 40), color, -1)
    label = state.value if event is None else f"!! {event} !!"
    cv2.putText(frame, label, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    cv2.putText(frame, f"{fps:4.1f} fps", (w - 120, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    lines = [f"vel_y:  {vel_y:+.2f}",     # pose centroid speed — the fall signature
             f"accel:  {accel_y:+.2f}"]   # impact (derivative of vel_y)
    if b is not None:
        lines += [
            f"posture:{b.stable_label}",
            f"motion: {b.motion:.2f}",
        ]
    else:
        lines.append("(no person box)")
    if distress_reason:
        lines.append(f"distress: {distress_reason}")
    for i, ln in enumerate(lines):
        y = 65 + i * 22
        cv2.putText(frame, ln, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
        cv2.putText(frame, ln, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    return frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0", help="webcam index (e.g. 0) or video path")
    ap.add_argument("--model", default="models/best.pt", help="YOLO posture model")
    ap.add_argument("--pose-model", default="models/pose_landmarker_heavy.task",
                    help="MediaPipe pose model (heavy=most accurate keypoints on floor poses)")
    ap.add_argument("--conf", type=float, default=0.35, help="YOLO confidence threshold")
    ap.add_argument("--imgsz", type=int, default=480, help="YOLO input size (smaller=faster)")
    ap.add_argument("--room-id", default="ROOM-1", help="room label attached to alerts")
    ap.add_argument("--alerts-dir", default="alerts", help="folder for fall snapshots + log")
    ap.add_argument("--webhook", default=None,
                    help="optional URL to POST alerts to (else ALERT_WEBHOOK env, else local only)")
    ap.add_argument("--snap-every", type=float, default=10.0,
                    help="auto-save an annotated snapshot every N seconds (0 = off)")
    ap.add_argument("--snap-dir", default="debugs", help="folder for auto snapshots")
    ap.add_argument("--save", default=None, help="write annotated video to this path")
    ap.add_argument("--no-display", action="store_true", help="don't open a window")
    ap.add_argument("--esp32-port", default="/dev/ttyUSB0",
                    help="serial port of the ESP32 buzzer/LED alert unit")
    ap.add_argument("--no-esp32", action="store_true",
                    help="don't drive the ESP32 buzzer/LED unit")
    ap.add_argument("--api-port", type=int, default=8080,
                    help="port for the JSON status API (tunnel with ngrok http <port>)")
    ap.add_argument("--no-api", action="store_true",
                    help="don't start the HTTP status API")
    args = ap.parse_args()

    source = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        sys.exit(f"ERROR: could not open source {args.source!r}.")

    # WSL2/usbipd webcams hand back green frames over YUYV; MJPG gives real data.
    if isinstance(source, int):
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    nominal_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    is_file = isinstance(source, str)

    from pose import PoseModel
    yolo = YoloFallModel(args.model, conf=args.conf, imgsz=args.imgsz)
    pose = PoseModel(args.pose_model)
    detector = FallDetector()
    alerts = AlertSink(room_id=args.room_id, out_dir=args.alerts_dir, webhook=args.webhook)
    esp32 = Esp32Alerter(port=args.esp32_port, enabled=not args.no_esp32)
    api = StatusServer(port=args.api_port, room_id=args.room_id, enabled=not args.no_api)

    writer = None
    if args.save:
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        writer = cv2.VideoWriter(args.save, cv2.VideoWriter_fourcc(*"mp4v"),
                                 nominal_fps if nominal_fps > 0 else 30.0, (w, h))

    if args.snap_every > 0:
        os.makedirs(args.snap_dir, exist_ok=True)

    tracker = BoxTracker()
    prev_kps = None
    cy_hist = deque(maxlen=3)
    pose_missing = 0
    frame_idx = 0
    snap_idx = 0
    last_snap_t = 0.0
    disp_fps = 10.0
    start_t = time.monotonic()
    last_t = start_t
    print(f"Source open. YOLO={os.path.basename(args.model)} imgsz={args.imgsz}. (q to quit)")

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]

        # REAL elapsed time per processed frame (the loop runs slower than the
        # camera's nominal fps, so velocity must use the measured dt). For a file
        # we trust its nominal fps instead.
        now = time.monotonic()
        dt = (1.0 / nominal_fps) if (is_file and nominal_fps > 0) else (now - last_t)
        dt = min(max(dt, 1e-3), 0.5)
        last_t = now
        timestamp_ms = int((now - start_t) * 1000) + frame_idx  # strictly increasing

        det = yolo.detect(frame)
        b = tracker.update(det, w, h)

        kps = pose.detect(frame, timestamp_ms)
        f = feat.compute(kps, w, h, prev_kps, cy_hist, dt, pose_missing)
        if f is not None:
            prev_kps = kps
            pose_missing = 0
        else:
            pose_missing += 1

        if b is None and f is None:
            state = detector.update_absent()
        else:
            state = detector.update(b, f)
        event = detector.last_event
        if event:
            print(f"[frame {frame_idx}] *** {event} ***")

        # Drive the physical alert unit (buzzer + red/blue LEDs) from the state.
        esp32.update(state)

        # Publish the same result over HTTP for external consumers (PHP site, etc.).
        api.publish(
            state=state.value,
            event=event,
            alert=state in (State.FALL, State.DISTRESS),
            person_present=b is not None,
            posture=(b.stable_label if b is not None else None),
            posture_confidence=(b.conf if b is not None else 0.0),
            motion=(b.motion if b is not None else 0.0),
            velocity_y=(f.velocity_y if f is not None else 0.0),
            distress=detector.distress,
            distress_reason=detector.distress_reason,
            long_lie=detector.long_lie,
            frame=frame_idx,
        )

        disp_fps += 0.1 * (1.0 / dt - disp_fps)

        vel = f.velocity_y if f is not None else 0.0
        banner_event = "LONG LIE: no recovery" if detector.long_lie else event
        draw_box(frame, b)
        draw_overlay(frame, b, vel, detector.accel_y, state, banner_event, disp_fps,
                     detector.distress_reason if detector.distress else "")

        # On a confirmed event, save an annotated snapshot + dispatch to emergency support.
        if event:
            alerts.fire(frame, event)

        # Hands-free periodic snapshot of the annotated frame.
        if args.snap_every > 0 and now - last_snap_t >= args.snap_every:
            last_snap_t = now
            path = os.path.join(args.snap_dir, f"snap_{snap_idx:03d}_{state.value}.png")
            cv2.imwrite(path, frame)
            print(f"[snap] {path}")
            snap_idx += 1

        if writer:
            writer.write(frame)
        if not args.no_display:
            cv2.imshow("Fall Detection", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        frame_idx += 1

    cap.release()
    if writer:
        writer.release()
        print(f"Saved annotated video to {args.save}")
    if not args.no_display:
        cv2.destroyAllWindows()
    pose.close()
    esp32.close()
    api.close()


if __name__ == "__main__":
    main()
