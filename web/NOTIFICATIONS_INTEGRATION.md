# Fall-Detection → Notifications: Integration Brief

**Goal:** notify a nurse/user when the fall-detection system raises an alert
(a patient fall or a distress gesture). This document is everything needed to
build that notification layer. You only consume a read-only JSON API — you do
not touch the camera, the model, or any hardware.

---

## 1. What the system does

A laptop runs a computer-vision model on a webcam and continuously classifies a
person's state (standing, sitting, fallen, etc.). When it detects a **fall** or
a **distress gesture**, it raises an alert. That alert is what you turn into a
notification.

The result is exposed as a small HTTP/JSON API. You **poll** it.

---

## 2. Connection details

- **Base URL:** provided separately (an `https://….ngrok-free.app` address).
  - ⚠️ This URL **changes every time the tunnel restarts** — store it as a
    config value / environment variable. Never hardcode it.
- **Auth:** none.
- **CORS:** open, so browser `fetch()` works from any origin.
- **Required header on every request:** `ngrok-skip-browser-warning: true`
  - Without it, the tunnel may return an HTML interstitial page instead of JSON.

If a request returns HTTP `502`, the detector isn't running (camera/model is
offline) — treat that as "monitoring unavailable".

---

## 3. Endpoints

### `GET /api/status` — current state (poll this)
Returns the latest result. Poll **every 1–2 seconds**.

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

Fields that matter for notifications:

| Field | Type | Use |
|---|---|---|
| `alert` | boolean | **Primary trigger.** `true` = emergency happening right now |
| `event` | string \| null | The headline for the notification (see §5). `null` when nothing just fired |
| `state` | string | Context: `STANDING`/`SITTING`/`LYING`/`FALLING`/`FALL`/`DISTRESS`/`ABSENT` |
| `room_id` | string | Which room/camera — include in the notification |
| `ts_ms` | integer | Epoch ms of this reading — use for de-duplication |
| `updated_at` | string | Human-readable time for the message body |

### `GET /api/events` — alert history
Most-recent-first list (max 50). Good for a notification feed / de-duplication.
```json
{ "events": [
  { "event": "FALL", "state": "FALL", "room_id": "ROOM-1",
    "ts_ms": 1781775067467, "at": "2026-06-18T12:31:07" }
] }
```

### `GET /api/health` — liveness
```json
{ "status": "ok", "time": "2026-06-18T12:31:07" }
```

---

## 4. How to turn polling into notifications (the important part)

The API is a *live status*, not a push queue — so `alert` stays `true` for the
whole duration of an emergency (could be many seconds = many polls). **Do not
send a notification on every poll.** Fire once per event, using edge-detection.

**Recommended algorithm (poll loop):**

```
remember last_notified_ts = 0

every 1–2 seconds:
    fetch /api/status   (with the ngrok header)
    if request failed or 502:
        mark "monitoring offline" (optional: notify once)
        continue

    if status.alert == true AND status.ts_ms != last_notified_ts:
        # a fresh alert is active and we haven't notified for THIS reading
        if last_notified_ts == 0 OR (status.ts_ms - last_notified_ts) > 15000:
            send_notification(status)        # see §5
            last_notified_ts = status.ts_ms

    if status.alert == false:
        last_notified_ts = 0                 # reset so the next alert notifies
```

- The `> 15000` (15s) cooldown stops re-notifying while the same emergency is
  ongoing, but still re-fires if the person falls again later. Tune to taste.
- Alternative (cleaner if you prefer): poll `/api/events`, keep the newest
  `ts_ms` you've seen, and notify for any event with a larger `ts_ms`. This
  naturally de-duplicates and gives you distinct fall vs distress events.

---

## 5. What to put in the notification

Map `event` (or `state`) to a message. Always include `room_id` and the time.

| `event` value | Suggested notification |
|---|---|
| `"FALL"` | 🚨 **Fall detected** in {room_id} at {updated_at} |
| `"LONG LIE: no recovery"` | 🚨 **Patient down and not moving** in {room_id} — {updated_at} |
| `"DISTRESS: arms overhead"` | ⚠️ **Distress signal (arms overhead)** in {room_id} — {updated_at} |
| `"DISTRESS: waving"` | ⚠️ **Distress signal (waving)** in {room_id} — {updated_at} |

If `event` is `null` but `alert` is `true`, fall back to a generic
"Emergency in {room_id}" using `state`.

The delivery channel (push, SMS, email, in-app toast, websocket to a dashboard)
is your choice — this API is channel-agnostic.

---

## 6. Code snippets

**JavaScript (browser / Node):**
```javascript
const BASE = process.env.FALL_API_BASE; // the ngrok https URL
let lastTs = 0;
const H = { "ngrok-skip-browser-warning": "true" };

setInterval(async () => {
  let s;
  try { s = await (await fetch(`${BASE}/api/status`, { headers: H })).json(); }
  catch { return; }                       // detector offline
  if (s.alert && s.ts_ms !== lastTs && (lastTs === 0 || s.ts_ms - lastTs > 15000)) {
    notify(s);                            // your channel
    lastTs = s.ts_ms;
  }
  if (!s.alert) lastTs = 0;
}, 1500);
```

**PHP (server-side poll, e.g. a cron or worker):**
```php
$base = getenv('FALL_API_BASE');
$ctx = stream_context_create(['http' => [
  'header' => "ngrok-skip-browser-warning: true\r\n", 'timeout' => 8,
]]);
$json = @file_get_contents("$base/api/status", false, $ctx);
if ($json === false) { /* monitoring offline */ exit; }
$s = json_decode($json, true);
if ($s['alert']) {
  // de-dup against your stored last ts_ms, then send the notification
  // message via $s['event'], $s['room_id'], $s['updated_at']
}
```

---

## 7. Quick checklist

- [ ] Base URL stored in config (not hardcoded) — it rotates on restart
- [ ] `ngrok-skip-browser-warning: true` header on every request
- [ ] Poll `/api/status` every 1–2s
- [ ] Edge-detect: notify once per alert (use `ts_ms` + a cooldown)
- [ ] Reset the de-dup marker when `alert` returns to `false`
- [ ] Handle request failure / `502` as "monitoring offline"
- [ ] Include `room_id` and time in every notification
