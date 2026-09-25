# ESP32 physical alert unit

A buzzer + red/blue LED box driven by the fall detector over USB serial.

| State (from detector) | Command | Blue LED | Red LED | Buzzer |
|---|---|---|---|---|
| STANDING / SITTING | `OK` | solid | off | off |
| LYING / FALLING (fallen, controlled) | `WARN` | off | slow blink | off |
| **FALL / DISTRESS / LONG LIE** | `ALERT` | off | **fast blink** | **on (pulsing)** |
| ABSENT (no person) | `ABSENT` | slow blink | off | off |
| laptop not running / unplugged | — (watchdog) | fast blink | off | off |

## 1. Wiring (ESP32 DevKit v1, 30-pin)

```
GPIO23 (D23) ──[220–330 Ω]──►|── GND     RED LED   (anode = long leg to resistor)
GPIO22 (D22) ──[220–330 Ω]──►|── GND     BLUE LED
GPIO21 (D21) ───────────────  buzzer +   ;  buzzer − ── GND
```

- Use any **GND** pin on the board (there are several).
- LEDs **must** have the series resistor or they (and the pin) can be damaged.
- A small **piezo** buzzer can be driven straight from the GPIO (low current).
  If yours is a louder electromagnetic buzzer drawing >40 mA, drive it through
  an NPN transistor (e.g. 2N2222: GPIO→1 kΩ→base, emitter→GND, collector→buzzer−,
  buzzer+→3V3) instead of directly.

## 2. Flash the firmware (Arduino IDE, on Windows)

1. Install the **esp32 by Espressif** boards package (Boards Manager).
2. Install the USB-UART driver if the port doesn't appear: **CP210x** (Silicon
   Labs) or **CH340/CH9102** — check Windows Device Manager to see which chip.
3. Open `firmware/esp32_alert/esp32_alert.ino`.
4. Board: **ESP32 Dev Module**. Select the COM port. Upload speed 115200.
5. If `BUZZER_PASSIVE` is wrong for your buzzer (sound is weak/odd), flip the
   one `const bool BUZZER_PASSIVE` flag at the top and re-upload.
6. On power-up it blinks blue then red once (wiring self-test).

## 3. Make the ESP32 visible to WSL2

You already do this for the webcam. The ESP32 is the same — and it can only be
attached to **one** place at a time, so flash from Windows Arduino IDE first,
then hand the port to WSL.

In an **admin PowerShell on Windows**:
```powershell
usbipd list                              # find the ESP32 (CP210x / CH340 / USB-SERIAL), note BUSID
usbipd bind   --busid <BUSID>            # once per device
usbipd attach --wsl --busid <BUSID>
```
In **WSL**:
```bash
ls -l /dev/ttyUSB0                       # should now exist
```

## 4. Run

```bash
python src/run.py --source 0             # uses /dev/ttyUSB0 by default
python src/run.py --source 0 --esp32-port /dev/ttyUSB1   # if it enumerated elsewhere
python src/run.py --source 0 --no-esp32  # run detection without the hardware
```

If the unit can't be opened, detection still runs and you'll see a one-line
`[esp32] ...` warning — the hardware is fully optional.
