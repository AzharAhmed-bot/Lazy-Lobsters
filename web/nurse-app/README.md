# Nurse Alert Dashboard (React + Vite)

A nurse-facing dashboard that polls the fall-detection API and raises a
notification (on-screen banner + sound + desktop notification) when a fall or
distress is detected. Shows the room number on every alert.

> ⚠️ This needs `npm install`, which requires internet access to the npm
> registry. If your current network blocks it, install on a different network
> (phone hotspot / home). Once installed, it runs offline against the API.

## Setup

```bash
cd web/nurse-app
cp .env.example .env        # then edit .env
npm install
npm run dev                 # opens http://localhost:5173
```

## Configure (`.env`)

| Var | Meaning | Example |
|---|---|---|
| `VITE_FALL_API_BASE` | Base URL of the fall API | `http://localhost:8090` or the ngrok `https://…` URL |
| `VITE_DEFAULT_ROOM` | Room shown if the API sends no `room_id` | `ROOM-101` |
| `VITE_POLL_MS` | Status poll interval (ms) | `1500` |

- Using the **ngrok** URL? It changes on every restart — update `.env` and
  restart `npm run dev`. The app already sends the `ngrok-skip-browser-warning`
  header for you.

## How it works

- Polls `GET /api/status` every `VITE_POLL_MS`.
- Fires a notification **once per emergency** (edge-detected on `ts_ms`, with a
  15s cooldown so an ongoing fall doesn't spam) — see `src/useFallStatus.js`.
- `GET /api/events` populates the "Recent alerts" feed.
- Click **🔔 Enable alerts** once on load — browsers require a user gesture
  before they allow sound and will prompt for notification permission.

## Notes / limitations

- **Desktop notifications + audio** need the page served over `http://localhost`
  or HTTPS (browser rule). `npm run dev` on localhost satisfies this.
- The room number comes from the API's `room_id`; `VITE_DEFAULT_ROOM` is only a
  fallback. To hard-set the room per station, change `VITE_DEFAULT_ROOM`.
- No auth on the API — fine for a demo, not for real patient data.

## Files

```
src/config.js         env + constants
src/notify.js         desktop notification + Web Audio alarm
src/useFallStatus.js  polling hook + once-per-alert edge detection
src/App.jsx           dashboard UI (room card, status, banner, events feed)
src/styles.css        styling (calm / warning / critical screen states)
```
