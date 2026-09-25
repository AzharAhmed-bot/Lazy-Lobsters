<?php
// Live webcam viewer — PHP serves the page; the camera runs in the visitor's
// browser via getUserMedia (JS). Expose this with a tunnel (ngrok) for an
// HTTPS URL, which the browser requires before it will grant camera access.
//
// Run locally:   php -S 0.0.0.0:8000 -t web
// Then tunnel:   ngrok http 8000   ->  open the https://… URL it prints
//
// Tiny JSON API endpoint (handy for health checks / the tunnel):
//   GET /index.php?api=health  ->  {"status":"ok","time":"..."}
if (isset($_GET['api']) && $_GET['api'] === 'health') {
    header('Content-Type: application/json');
    echo json_encode([
        'status' => 'ok',
        'time'   => date('c'),
        'server' => 'Lazy-Lobsters webcam viewer',
    ]);
    exit;
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Live Webcam — Lazy Lobsters</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 16px;
    background: #0b0f17; color: #e6edf3;
    font: 16px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    padding: 16px;
  }
  h1 { font-size: 1.1rem; font-weight: 600; margin: 0; letter-spacing: .3px; }
  #wrap {
    position: relative; width: min(100%, 720px); aspect-ratio: 4 / 3;
    background: #000; border-radius: 14px; overflow: hidden;
    box-shadow: 0 10px 40px rgba(0,0,0,.5);
  }
  video { width: 100%; height: 100%; object-fit: cover; display: block; }
  video.mirror { transform: scaleX(-1); }
  #status {
    position: absolute; inset: 0; display: flex; align-items: center;
    justify-content: center; text-align: center; padding: 24px;
    color: #9aa7b4; font-size: .95rem;
  }
  #status.error { color: #ff8080; }
  .row { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
  button {
    background: #1f6feb; color: #fff; border: 0; border-radius: 10px;
    padding: 10px 18px; font-size: .95rem; cursor: pointer; font-weight: 600;
  }
  button.secondary { background: #21262d; color: #c9d1d9; }
  button:disabled { opacity: .45; cursor: default; }
</style>
</head>
<body>
  <h1>📷 Live Webcam</h1>
  <div id="wrap">
    <video id="video" autoplay playsinline muted></video>
    <div id="status">Tap “Start camera” and allow access.</div>
  </div>
  <div class="row">
    <button id="start">Start camera</button>
    <button id="flip" class="secondary" disabled>Switch camera</button>
    <button id="mirror" class="secondary" disabled>Mirror</button>
    <button id="stop" class="secondary" disabled>Stop</button>
  </div>

<script>
  const video  = document.getElementById('video');
  const status = document.getElementById('status');
  const btnStart = document.getElementById('start');
  const btnFlip  = document.getElementById('flip');
  const btnMirror= document.getElementById('mirror');
  const btnStop  = document.getElementById('stop');

  let stream = null;
  let facing = 'user';           // 'user' = front, 'environment' = back

  function setStatus(msg, isError) {
    status.textContent = msg;
    status.style.display = msg ? 'flex' : 'none';
    status.classList.toggle('error', !!isError);
  }

  async function start() {
    // getUserMedia needs HTTPS (or localhost). Over a plain http tunnel the
    // browser hides the API entirely, so guide the user instead of failing silently.
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setStatus('Camera API unavailable. Open this page over HTTPS (use the ngrok https:// link), not http://.', true);
      return;
    }
    stop();
    setStatus('Requesting camera…');
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: facing }, audio: false
      });
      video.srcObject = stream;
      setStatus('');                       // hide overlay -> video shows
      btnFlip.disabled = btnMirror.disabled = btnStop.disabled = false;
      btnStart.textContent = 'Restart';
    } catch (err) {
      if (err.name === 'NotAllowedError')      setStatus('Permission denied. Allow camera access in the browser and try again.', true);
      else if (err.name === 'NotFoundError')   setStatus('No camera found on this device.', true);
      else                                     setStatus('Could not start camera: ' + err.name + ' — ' + err.message, true);
    }
  }

  function stop() {
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
    video.srcObject = null;
    btnFlip.disabled = btnMirror.disabled = btnStop.disabled = true;
  }

  btnStart.onclick  = start;
  btnStop.onclick   = () => { stop(); setStatus('Camera stopped.'); };
  btnFlip.onclick   = () => { facing = (facing === 'user') ? 'environment' : 'user'; start(); };
  btnMirror.onclick = () => video.classList.toggle('mirror');
</script>
</body>
</html>
