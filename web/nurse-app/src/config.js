// All runtime config comes from .env (Vite exposes VITE_* vars), with safe
// fallbacks so the app still runs if no .env is present.

export const API_BASE = (import.meta.env.VITE_FALL_API_BASE || 'http://localhost:8090')
  .replace(/\/+$/, ''); // strip trailing slash

export const DEFAULT_ROOM = import.meta.env.VITE_DEFAULT_ROOM || 'ROOM-101';

export const POLL_MS = Number(import.meta.env.VITE_POLL_MS || 1500);

// Don't re-notify for the same ongoing emergency more often than this.
export const ALERT_COOLDOWN_MS = 15000;

// ngrok serves an HTML interstitial unless this header is present.
export const REQUEST_HEADERS = { 'ngrok-skip-browser-warning': 'true' };
