"""Alert sink: on a confirmed event, capture evidence and dispatch it.

When the detector fires a FALL / LONG LIE / DISTRESS, a nurse needs three things
fast: WHERE (room), WHEN (timestamp) and WHAT it looked like (a snapshot). This
module turns an event + the current annotated frame into:

  1. a JPEG snapshot saved under alerts/  (the annotated frame: skeleton + box +
     banner — never the raw video, keeping the project's privacy stance),
  2. an append-only JSONL audit record (room_id, ISO timestamp, type, path),
  3. a dispatch() call to "emergency support" — a stub that logs, and POSTs to a
     webhook if ALERT_WEBHOOK is set (no network by default, so the demo is offline-safe).

De-duplication: the same ongoing event (e.g. a patient who stays fallen) must not
spam one snapshot per frame. We fire once per event type and re-arm only after the
event has cleared for COOLDOWN_SECONDS.
"""
import base64
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

import cv2

COOLDOWN_SECONDS = 15.0   # don't re-fire the same event type until it's been clear this long


class AlertSink:
    def __init__(self, room_id="ROOM-1", out_dir="alerts", webhook=None):
        # room_id lands in snapshot filenames; keep it filesystem-safe (no path traversal).
        self.room_id = "".join(c if (c.isalnum() or c in "-_") else "_"
                               for c in str(room_id)) or "ROOM"
        self.out_dir = out_dir
        self.webhook = webhook or os.environ.get("ALERT_WEBHOOK")
        self._last_fired = {}     # event-type -> monotonic time it last fired
        os.makedirs(out_dir, exist_ok=True)
        self.log_path = os.path.join(out_dir, "alerts.jsonl")

    def _classify(self, event):
        """Map a raw detector event string to a stable alert type, or None to skip."""
        if event is None:
            return None
        e = event.upper()
        if e.startswith("FALL"):
            return "FALL"
        if "LONG LIE" in e:
            return "LONG_LIE"
        if e.startswith("DISTRESS"):
            return "DISTRESS"
        return None

    def fire(self, frame, event):
        """Handle one detector event. Returns the alert record dict if dispatched,
        else None (unknown event, or still within the per-type cooldown)."""
        atype = self._classify(event)
        if atype is None:
            return None

        now = time.monotonic()
        last = self._last_fired.get(atype, -1e9)
        if now - last < COOLDOWN_SECONDS:
            return None
        self._last_fired[atype] = now

        ts = datetime.now(timezone.utc)
        stamp = ts.strftime("%Y%m%d_%H%M%S")
        fname = f"{stamp}_{self.room_id}_{atype}.jpg"
        fpath = os.path.join(self.out_dir, fname)
        # cv2.imwrite returns False (no exception) on failure; treat that as "no snapshot"
        # rather than recording a path to a file that isn't there. The whole block is
        # guarded so unhealthy storage can NEVER crash the detection loop after a fall.
        try:
            if frame is not None and cv2.imwrite(fpath, frame):
                snapshot = fpath
            else:
                snapshot = None
                if frame is not None:
                    print(f"[ALERT] WARNING: could not write snapshot {fpath}")
        except Exception as exc:   # noqa: BLE001 — never let evidence I/O kill detection
            snapshot = None
            print(f"[ALERT] WARNING: snapshot write raised ({exc})")

        record = {
            "room_id": self.room_id,
            "timestamp": ts.isoformat(),
            "type": atype,
            "detail": event,
            "snapshot": snapshot,
        }
        try:
            with open(self.log_path, "a") as fh:
                fh.write(json.dumps(record) + "\n")
        except OSError as exc:
            print(f"[ALERT] WARNING: could not write audit log ({exc}); alert still dispatched")

        self.dispatch(record, frame)
        return record

    def dispatch(self, record, frame):
        """Hand the alert to emergency support. Logs locally; if a webhook URL is
        configured, POSTs the record (with a base64 snapshot) to it. Network errors
        are swallowed so a flaky link never crashes the monitoring loop."""
        print(f"[ALERT] *** {record['type']} *** room={record['room_id']} "
              f"at {record['timestamp']} -> {record['snapshot']}")
        if not self.webhook:
            return
        payload = dict(record)
        if frame is not None:
            ok, buf = cv2.imencode(".jpg", frame)
            if ok:
                payload["snapshot_b64"] = base64.b64encode(buf).decode("ascii")
        try:
            req = urllib.request.Request(
                self.webhook,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=3)
            print(f"[ALERT] dispatched to {self.webhook}")
        except Exception as exc:   # noqa: BLE001 — never let dispatch kill detection
            print(f"[ALERT] webhook dispatch failed ({exc}); alert still saved locally")
