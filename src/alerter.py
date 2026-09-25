"""USB-serial bridge from the fall detector to the ESP32 alert unit.

Maps the detector's State to one of four commands and writes it to the ESP32
over USB serial. Commands are sent only when the command CHANGES, plus a
once-a-second heartbeat so the ESP32's link-lost watchdog stays fed and so a
freshly-rebooted ESP32 re-syncs to the current state.

Hardware is OPTIONAL: if pyserial is missing or the port can't be opened, the
detector keeps running and this just becomes a no-op (a single warning is
printed). See firmware/esp32_alert/esp32_alert.ino for the receiving side.

State -> command:
    FALL, DISTRESS, LONG LIE  -> ALERT   (red fast blink + buzzer)
    LYING, FALLING            -> WARN    (red slow blink, no buzzer)
    STANDING, SITTING         -> OK      (blue solid)
    ABSENT                    -> ABSENT  (blue slow blink)
"""
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from detector import State  # noqa: E402

try:
    import serial  # pyserial
except ImportError:  # pragma: no cover - hardware optional
    serial = None

_STATE_TO_CMD = {
    State.FALL: "ALERT",
    State.DISTRESS: "ALERT",
    State.LYING: "WARN",
    State.FALLING: "WARN",
    State.STANDING: "OK",
    State.SITTING: "OK",
    State.ABSENT: "ABSENT",
}

HEARTBEAT_SECONDS = 1.0


class Esp32Alerter:
    """Thin, fail-soft wrapper around the serial link to the ESP32."""

    def __init__(self, port="/dev/ttyUSB0", baud=115200, enabled=True):
        self.ser = None
        self._last_cmd = None
        self._last_send = 0.0
        if not enabled:
            return
        if serial is None:
            print("[esp32] pyserial not installed (pip install pyserial) — "
                  "alert unit disabled.")
            return
        try:
            # short write timeout: a stuck USB write must never stall the
            # detection loop.
            self.ser = serial.Serial(port, baud, timeout=0.1, write_timeout=0.2)
            time.sleep(2.0)  # ESP32 auto-resets when the port opens; let it boot
            print(f"[esp32] alert unit connected on {port} @ {baud}")
        except Exception as e:  # serial.SerialException and friends
            print(f"[esp32] could not open {port} ({e}) — alert unit disabled. "
                  "On WSL2, attach it with: usbipd attach --busid <id> --wsl")
            self.ser = None

    def _write(self, cmd):
        try:
            self.ser.write((cmd + "\n").encode("ascii"))
        except Exception as e:  # disconnected mid-run -> stop trying, keep detecting
            print(f"[esp32] write failed ({e}) — disabling alert unit.")
            try:
                self.ser.close()
            finally:
                self.ser = None

    def update(self, state):
        """Call once per frame with the detector's display_state."""
        if self.ser is None:
            return
        cmd = _STATE_TO_CMD.get(state, "OK")
        now = time.monotonic()
        if cmd != self._last_cmd or (now - self._last_send) >= HEARTBEAT_SECONDS:
            self._write(cmd)
            self._last_cmd = cmd
            self._last_send = now

    def close(self):
        if self.ser is not None:
            try:
                self._write("OK")  # leave it in a calm state
                self.ser.close()
            except Exception:
                pass
            self.ser = None
