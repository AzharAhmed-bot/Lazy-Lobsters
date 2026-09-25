import { useCallback, useEffect, useState } from 'react';
import { useFallStatus } from './useFallStatus';
import { DEFAULT_ROOM } from './config';
import { requestNotifyPermission, unlockAudio, showNotification, alarm } from './notify';

// Map an event/state to a headline + severity for the banner & notification.
function alertInfo(s) {
  if (!s) return null;
  if (s.event === 'FALL') return { title: '🚨 Fall detected', level: 'critical' };
  if (s.event === 'LONG LIE: no recovery') return { title: '🚨 Patient down — not moving', level: 'critical' };
  if (s.event && s.event.startsWith('DISTRESS')) return { title: '⚠️ Distress signal', level: 'warning' };
  if (s.alert) return { title: '🚨 Emergency', level: 'critical' };
  return null;
}

const STATE_LABEL = {
  STANDING: 'Standing', SITTING: 'Sitting', LYING: 'Lying down',
  FALLING: 'Falling', FALL: 'FALL', DISTRESS: 'Distress', ABSENT: 'No one present',
};

function fmtTime(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleTimeString(); } catch { return iso; }
}

export default function App() {
  const [armed, setArmed] = useState(false);     // notifications enabled by the nurse
  const [banner, setBanner] = useState(null);    // active emergency banner

  const handleAlert = useCallback((s) => {
    const info = alertInfo(s);
    const room = s.room_id || DEFAULT_ROOM;
    alarm(3);
    showNotification(info?.title || 'Emergency', `${room} • ${s.event || s.state} • ${fmtTime(s.updated_at)}`);
    setBanner({ ...s, info });
  }, []);

  const { status, online, events } = useFallStatus(handleAlert);

  // auto-clear the banner once the emergency is over
  useEffect(() => {
    if (status && !status.alert) setBanner(null);
  }, [status]);

  const room = status?.room_id || DEFAULT_ROOM;
  const isAlert = !!status?.alert;
  const info = alertInfo(status);
  const screenClass = isAlert
    ? (info?.level === 'warning' ? 'screen warning' : 'screen critical')
    : 'screen calm';

  async function enableNotifications() {
    unlockAudio();           // must happen in a click handler
    await requestNotifyPermission();
    alarm(1);                // confirmation blip
    setArmed(true);
  }

  return (
    <div className={screenClass}>
      <header className="topbar">
        <div className="brand">🏥 Nurse Alert Dashboard</div>
        <div className="conn">
          <span className={online ? 'dot dot-on' : 'dot dot-off'} />
          {online ? 'Monitoring live' : 'Monitoring offline'}
        </div>
      </header>

      {!armed && (
        <button className="enable" onClick={enableNotifications}>
          🔔 Enable alerts (sound + notifications)
        </button>
      )}

      {banner && (
        <div className={`banner ${banner.info?.level || 'critical'}`}>
          <div className="banner-title">{banner.info?.title || 'Emergency'}</div>
          <div className="banner-room">Room {banner.room_id || DEFAULT_ROOM}</div>
          <div className="banner-time">{fmtTime(banner.updated_at)}</div>
          <button className="ack" onClick={() => setBanner(null)}>Acknowledge</button>
        </div>
      )}

      <main className="grid">
        <section className="card room-card">
          <div className="card-label">Room</div>
          <div className="room-number">{room}</div>
        </section>

        <section className="card status-card">
          <div className="card-label">Current status</div>
          <div className="status-value">
            {status ? (STATE_LABEL[status.state] || status.state) : '—'}
          </div>
          <div className="status-sub">
            {status?.person_present ? 'Person present' : 'No person in view'}
            {status?.distress ? ` • distress: ${status.distress_reason}` : ''}
          </div>
          {!online && <div className="status-sub offline">Detector not reachable — check the camera laptop / tunnel.</div>}
        </section>
      </main>

      <section className="card events">
        <div className="card-label">Recent alerts</div>
        {events.length === 0 && <div className="muted">No alerts yet.</div>}
        <ul>
          {events.map((e, i) => (
            <li key={`${e.ts_ms}-${i}`}>
              <span className={`tag ${e.event?.startsWith('DISTRESS') ? 'warning' : 'critical'}`}>
                {e.event}
              </span>
              <span className="ev-room">Room {e.room_id || DEFAULT_ROOM}</span>
              <span className="ev-time">{fmtTime(e.at)}</span>
            </li>
          ))}
        </ul>
      </section>

      <footer className="foot">
        Polling the fall-detection API • room falls back to <b>{DEFAULT_ROOM}</b> when the API sends none.
      </footer>
    </div>
  );
}
