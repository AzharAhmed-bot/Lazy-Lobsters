"""Network-facing status API for the fall detector — dependency-free (stdlib).

The detector owns the webcam and the model. This publishes its live result over
HTTP/JSON so anyone else can read it — e.g. a PHP website polling from another
host. It is the network twin of alerter.py (which pushes the same state to the
ESP32 over serial).

Runs in a background thread inside run.py; nothing here blocks the detector.
CORS is wide-open (Access-Control-Allow-Origin: *) so a browser on any origin
can fetch it.

Endpoints (all GET):
    /api/status   latest detection result (poll this ~1/sec)
    /api/events   recent alert events (most-recent first)
    /api/health   {"status":"ok"}

Expose it externally with a tunnel:  ngrok http 8080
"""
import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


class _Shared:
    def __init__(self, room_id):
        self.lock = threading.Lock()
        self.events = deque(maxlen=50)
        self.latest = {
            "state": "STANDING", "event": None, "alert": False,
            "person_present": False, "posture": None, "posture_confidence": 0.0,
            "motion": 0.0, "velocity_y": 0.0, "distress": False,
            "distress_reason": "", "long_lie": False, "room_id": room_id,
            "frame": 0, "ts_ms": 0, "updated_at": None,
        }


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def do_GET(self):
        shared = self.server.shared
        path = self.path.split("?", 1)[0].rstrip("/")
        if path == "/api/status":
            with shared.lock:
                self._send(200, dict(shared.latest))
        elif path == "/api/events":
            with shared.lock:
                self._send(200, {"events": list(shared.events)})
        elif path in ("/api/health", "/api"):
            self._send(200, {"status": "ok", "time": _iso()})
        else:
            self._send(404, {"status": "error", "message": "not found",
                             "endpoints": ["/api/status", "/api/events", "/api/health"]})

    def log_message(self, *args):   # keep the detector's console clean
        pass


class StatusServer:
    def __init__(self, host="0.0.0.0", port=8080, room_id="ROOM-1", enabled=True):
        self._httpd = None
        self.shared = _Shared(room_id)
        if not enabled:
            return
        try:
            self._httpd = ThreadingHTTPServer((host, port), _Handler)
            self._httpd.shared = self.shared
            threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
            print(f"[api] status API on http://{host}:{port}/api/status "
                  f"(tunnel it with: ngrok http {port})")
        except Exception as e:
            print(f"[api] could not start status API on {host}:{port} ({e}) — disabled.")
            self._httpd = None

    def publish(self, *, state, event, alert, person_present, posture,
                posture_confidence, motion, velocity_y, distress,
                distress_reason, long_lie, frame):
        if self._httpd is None:
            return
        snap = {
            "state": state, "event": event, "alert": bool(alert),
            "person_present": bool(person_present), "posture": posture,
            "posture_confidence": round(float(posture_confidence), 3),
            "motion": round(float(motion), 3),
            "velocity_y": round(float(velocity_y), 3),
            "distress": bool(distress), "distress_reason": distress_reason or "",
            "long_lie": bool(long_lie), "room_id": self.shared.latest["room_id"],
            "frame": int(frame), "ts_ms": int(time.time() * 1000),
            "updated_at": _iso(),
        }
        with self.shared.lock:
            self.shared.latest = snap
            if event:
                self.shared.events.appendleft({
                    "event": event, "state": state, "room_id": snap["room_id"],
                    "ts_ms": snap["ts_ms"], "at": snap["updated_at"],
                })

    def close(self):
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
            finally:
                self._httpd = None
