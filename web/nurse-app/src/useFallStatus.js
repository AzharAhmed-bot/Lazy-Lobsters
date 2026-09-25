import { useEffect, useRef, useState } from 'react';
import { API_BASE, POLL_MS, ALERT_COOLDOWN_MS, REQUEST_HEADERS } from './config';

// Polls /api/status and /api/events. Calls onAlert(status) ONCE per emergency
// (edge-detected via ts_ms + cooldown), not on every poll.
export function useFallStatus(onAlert) {
  const [status, setStatus] = useState(null);
  const [online, setOnline] = useState(false);
  const [events, setEvents] = useState([]);

  const lastNotifiedTs = useRef(0);
  const onAlertRef = useRef(onAlert);
  onAlertRef.current = onAlert;

  // live status
  useEffect(() => {
    let stop = false;
    async function tick() {
      try {
        const r = await fetch(`${API_BASE}/api/status`, { headers: REQUEST_HEADERS });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const s = await r.json();
        if (stop) return;
        setStatus(s);
        setOnline(true);

        const fresh =
          s.alert &&
          s.ts_ms !== lastNotifiedTs.current &&
          (lastNotifiedTs.current === 0 || s.ts_ms - lastNotifiedTs.current > ALERT_COOLDOWN_MS);
        if (fresh) {
          lastNotifiedTs.current = s.ts_ms;
          onAlertRef.current?.(s);
        }
        if (!s.alert) lastNotifiedTs.current = 0; // reset so the next alert fires
      } catch {
        if (!stop) setOnline(false); // detector down / network issue
      }
    }
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => { stop = true; clearInterval(id); };
  }, []);

  // recent events feed (polled less often)
  useEffect(() => {
    let stop = false;
    async function load() {
      try {
        const r = await fetch(`${API_BASE}/api/events`, { headers: REQUEST_HEADERS });
        if (r.ok) {
          const d = await r.json();
          if (!stop) setEvents(d.events || []);
        }
      } catch { /* ignore */ }
    }
    load();
    const id = setInterval(load, 4000);
    return () => { stop = true; clearInterval(id); };
  }, []);

  return { status, online, events };
}
