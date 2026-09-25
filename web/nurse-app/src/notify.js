// Notification helpers: desktop notifications + an audible alarm.
// Browsers block audio until a user gesture, so call unlockAudio() from a click.

let audioCtx = null;

export function unlockAudio() {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') audioCtx.resume();
  } catch { /* ignore */ }
}

export async function requestNotifyPermission() {
  if ('Notification' in window && Notification.permission === 'default') {
    try { return await Notification.requestPermission(); } catch { /* ignore */ }
  }
  return 'Notification' in window ? Notification.permission : 'unsupported';
}

export function showNotification(title, body) {
  if ('Notification' in window && Notification.permission === 'granted') {
    try { new Notification(title, { body, requireInteraction: true }); } catch { /* ignore */ }
  }
}

// Three short square-wave beeps via the Web Audio API (no audio file needed).
export function alarm(times = 3) {
  if (!audioCtx) return;
  let t = audioCtx.currentTime;
  for (let i = 0; i < times; i++) {
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = 'square';
    osc.frequency.value = 880;
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.35, t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.22);
    osc.start(t);
    osc.stop(t + 0.25);
    t += 0.32;
  }
}
