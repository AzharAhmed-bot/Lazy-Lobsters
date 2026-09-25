# Fall-Detection Status API

Read-only JSON API exposing the live result of the fall-detection model. The
detector owns the webcam and the model; you just poll these endpoints.

- **Base URL (local):** `http://localhost:8080`
- **Base URL (external):** the `https://….ngrok-free.app` URL from `ngrok http 8080`
  (changes each ngrok restart — make it a config value, don't hardcode).
- **Auth:** none. **CORS:** open (`Access-Control-Allow-Origin: *`), so browser
  `fetch()` works from any origin.
- **Prerequisite:** the detector must be running: `python3 src/run.py --source 0`.

---

## GET `/api/status`

The current model result. **Poll about once per second.**

### Input
None. Plain `GET`, no query params, no headers, no body.

### Response — `200 application/json`
```json
{
  "state": "FALL",
  "event": "FALL",
  "alert": true,
  "person_present": true,
  "posture": "FALLEN",
  "posture_confidence": 0.88,
  "motion": 0.05,
  "velocity_y": 1.4,
  "distress": false,
  "distress_reason": "",
  "long_lie": false,
  "room_id": "ROOM-1",
  "frame": 42,
  "ts_ms": 1781775067467,
  "updated_at": "2026-06-18T12:31:07"
}
```

| Field | Type | Meaning |
|---|---|---|
| `state` | string | One of: `STANDING`, `SITTING`, `LYING`, `FALLING`, `FALL`, `DISTRESS`, `ABSENT` |
| `event` | string \| null | Alert fired at this instant: `"FALL"`, `"LONG LIE: no recovery"`, `"DISTRESS: arms overhead"`, `"DISTRESS: waving"`, else `null` |
| `alert` | boolean | **Act on this.** `true` = emergency (fall or distress); the buzzer is sounding |
| `person_present` | boolean | A person is detected in frame |
| `posture` | string \| null | Raw posture: `STANDING`, `SITTING`, `FALLEN`, or `null` if no person |
| `posture_confidence` | number | 0.0–1.0 |
| `motion` | number | Movement amount (low = still) |
| `velocity_y` | number | Downward speed signal (high = fast drop) |
| `distress` | boolean | Distress gesture currently active |
| `distress_reason` | string | `"arms overhead"`, `"waving"`, or `""` |
| `long_lie` | boolean | Confirmed fall + prolonged immobility |
| `room_id` | string | Room label (default `ROOM-1`) |
| `frame` | integer | Frame counter |
| `ts_ms` | integer | Epoch milliseconds of this result |
| `updated_at` | string | ISO-8601 local time |

**Display rule:** if `alert == true` → show the emergency/red state; otherwise show `state`.

---

## GET `/api/events`

The most recent alert events only (max 50, newest first). Useful for a log/feed.

### Input
None.

### Response — `200 application/json`
```json
{
  "events": [
    {
      "event": "FALL",
      "state": "FALL",
      "room_id": "ROOM-1",
      "ts_ms": 1781775067467,
      "at": "2026-06-18T12:31:07"
    }
  ]
}
```
`events` is `[]` until the first alert occurs.

---

## GET `/api/health`

Liveness check.

### Input
None.

### Response — `200 application/json`
```json
{ "status": "ok", "time": "2026-06-18T12:31:07" }
```

---

## Errors

Unknown path → `404 application/json`:
```json
{ "status": "error", "message": "not found",
  "endpoints": ["/api/status", "/api/events", "/api/health"] }
```
If you get a `502` from the ngrok URL, the detector (`run.py`) isn't running.

---

## Examples

```bash
curl https://abc123.ngrok-free.app/api/status
curl https://abc123.ngrok-free.app/api/events
curl https://abc123.ngrok-free.app/api/health
```

```javascript
// browser / front-end polling
setInterval(async () => {
  const r = await fetch("https://abc123.ngrok-free.app/api/status");
  const s = await r.json();
  document.body.style.background = s.alert ? "red" : "#111";
  console.log(s.state, s.alert);
}, 1000);
```

```php
// PHP server-side poll
$json = file_get_contents("https://abc123.ngrok-free.app/api/status");
$s = json_decode($json, true);
if ($s["alert"]) { /* show emergency for $s["room_id"] */ }
```
