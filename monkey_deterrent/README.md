# Monkey Deterrent System — Raspberry Pi 4B

An autonomous, edge-only system that watches for monkeys with a camera, confirms
them with an on-device neural network, and drives an **ultrasonic deterrent** while
sending an annotated alert photo to Telegram — all running locally on a Raspberry Pi
4B with no cloud inference.

---

## 1. Overview (the short version)

A PIR motion sensor wakes the system only when something moves. The camera grabs a
frame, an object-detection model decides whether it's a monkey, and if it's confident
enough the Pi emits a randomized **20–40 kHz ultrasonic** burst (inaudible/irritating
to the animal) and pushes a photo to your phone via Telegram. When nothing is moving
the system sits nearly idle, which keeps the Pi cool and power-efficient.

```
PIR motion ──► capture frame ──► detect (NCNN/ONNX) ──► monkey? ──► confidence ≥ 0.85?
                                                                          │
                                                  ┌───────────────────────┴───────────────┐
                                                  ▼                                         ▼
                                        ultrasonic 20–40 kHz burst            Telegram alert (annotated photo)
```

Everything runs on the Pi. The only network use is the optional Telegram alert.

---

## 2. Hardware & wiring (BCM pin numbers)

| Component             | Pi pin            | Wiring notes                                            |
|-----------------------|-------------------|--------------------------------------------------------|
| PIR sensor (signal)   | GPIO17 (pin 11)   | VCC → 5V, GND → GND                                     |
| Ultrasonic module IN  | GPIO18 (pin 12)   | **PWM0 hardware-PWM pin.** VCC → 3V3 (pin 1), GND → GND |
| Pi Camera Module 2    | CSI ribbon port   | enable with `sudo raspi-config`                         |

> GPIO18 is one of only four hardware-PWM-capable pins. This matters — see §4.

---

## 3. Software architecture

| File                   | Responsibility                                                                 |
|------------------------|--------------------------------------------------------------------------------|
| `main.py`              | Orchestrates the loop: PIR gate → capture → detect → confidence gate → cooldown → alert + buzzer. Owns GPIO/thermal/signal handling. |
| `config.py`            | All tunables: pins, model paths/engine, thresholds, ultrasonic band, timing, Telegram env vars. |
| `detector_factory.py`  | Returns the configured detector; NCNN and ONNX share one `.detect(frame_rgb) -> [(x1,y1,x2,y2,score), …]` interface. |
| `inference_ncnn.py`    | NCNN backend (default — fastest on the Pi's ARM CPU).                           |
| `inference.py`         | ONNX Runtime backend (fallback).                                               |
| `buzzer.py`            | Ultrasonic deterrent driver via **pigpio hardware PWM**.                        |
| `telegram_notifier.py` | Fire-and-forget Telegram `sendPhoto` on a background thread.                    |
| `thermal.py`           | Reads SoC temperature and blocks (with hysteresis) when too hot.               |
| `live_preview.py`      | Desktop diagnostic — live camera window with detection boxes (needs a display).|
| `convert_model.py`     | Laptop-side: convert a `.pt` model to ONNX/NCNN.                               |

### Detection pipeline detail
- `picamera2` delivers `RGB888` frames (which arrive BGR in the array); `main.py`
  converts BGR→RGB before inference.
- The detector returns boxes with confidence scores. The detector's own
  `CONFIDENCE_THRESHOLD` (0.50) governs what counts as a *detection*; a separate,
  stricter `BUZZER_CONFIDENCE_THRESHOLD` (0.85) governs what actually *fires the
  deterrent + alert* — so you can detect liberally but act conservatively.

---

## 4. The ultrasonic deterrent (the tricky part)

### Why pigpio + hardware PWM
The deterrent emits a randomized **20–40 kHz** tone. Software PWM (`RPi.GPIO`) makes
its waveform by toggling a pin from a Python thread — far too jittery above a few kHz,
which produces audible crackle. **pigpio's `hardware_PWM` on GPIO18** uses the SoC's
dedicated PWM peripheral, so tones stay clean and jitter-free deep into the ultrasonic
band. Requires the `pigpiod` daemon.

### Smooth frequency sweep, not jumps
`sound_alarm()` does a **random walk**: it picks a random target in the band and
*glides* to it in small (~500 Hz) steps rather than jumping. An abrupt jump is a step
discontinuity that radiates an audible click; small ultrasonic steps keep all that
transient energy above 20 kHz (inaudible). The PWM is never dropped to 0 mid-burst
(another click source).

### The "airhorn" gotcha (idle pin must FLOAT)
The 3-pin transducer module (VCC/GND/IN) has its own onboard driver. Empirically:

| IN pin state                        | Result            |
|-------------------------------------|-------------------|
| Fed clean 20–40 kHz PWM             | silent (ultrasonic) ✓ |
| Floating / high-impedance           | silent ✓          |
| Held at a steady logic level (DC)   | **audible airhorn** ✗ |

So **idle = release GPIO18 to high-Z `INPUT` (no pull)** — electrically identical to
unplugging the IN wire. Driving the pin LOW is the *wrong* move; it triggers the
airhorn. `init_gpio()`, `Buzzer._off()`, and `cleanup()` all park the pin high-Z;
only `sound_alarm()`/`short_beep()` actively drive it.

### System audio must be off
GPIO18's PWM peripheral is shared with the Pi's analog audio driver (`snd_bcm2835`).
Leave onboard analog audio disabled so pigpio has exclusive control:
```bash
# /boot/firmware/config.txt
dtparam=audio=off
```
(HDMI audio is unaffected; only the 3.5 mm jack is lost.) Reboot after changing.

---

## 5. Thermal protection (built in)

1. **PIR gating** — frames are inferred only on motion; idle ≈ zero CPU, so the Pi
   stays cool most of the time.
2. **imgsz 416 + 10 fps** — keeps inference load (and heat) down.
3. **Thermal throttle** (`thermal.py`) — at ≥ `MAX_CPU_TEMP_C` (78 °C) inference
   blocks until the SoC drops 5 °C (73 °C) — hysteresis avoids ping-ponging.
4. **Detection cooldown** — `DETECTION_COOLDOWN` (15 s) between alarms avoids
   redundant inference/alarm bursts.

**Recommended:** a small heatsink + fan. Under sustained sun, passive cooling alone
may not be enough. Check temp anytime: `vcgencmd measure_temp`.

---

## 6. Telegram alerts (optional)

On a confirmed hit (≥ `BUZZER_CONFIDENCE_THRESHOLD`) the frame is annotated (red box +
confidence), JPEG-encoded **in memory** (no SD-card write), and sent via the Bot API
`sendPhoto` on a **background daemon thread** — the network call never blocks the
alarm or the loop, and any failure is logged, never raised. Unset credentials simply
disable alerts; the deterrent still runs.

**Setup**
1. Create a bot with [@BotFather](https://t.me/BotFather), copy the **token**.
2. Message your bot, then find your **chat_id**:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/getUpdates"   # read "chat":{"id":<NUMBER>}
   ```
3. Provide both as env vars (kept out of git):
   ```bash
   export TELEGRAM_BOT_TOKEN="123456:ABC-..."
   export TELEGRAM_CHAT_ID="<NUMBER>"
   ```

---

## 7. Setup & run

### On your LAPTOP — convert the model
PyTorch/ultralytics on the Pi's ARM CPU throws `Illegal instruction (SIGILL)` — never
run them on the Pi. Convert on the laptop instead:
```bash
pip install -r requirements_laptop.txt
python convert_model.py --weights macaque30epochs.pt --size 416
# copy the resulting .onnx / .ncnn.* files to the Pi
```

### On the Pi — install deps
```bash
sudo apt install pigpio python3-pigpio
sudo systemctl enable --now pigpiod

cd /home/bobby/iotmonkeyalert-model/monkey_deterrent
python3 -m venv --system-site-packages venv   # inherits apt picamera2
source venv/bin/activate
pip install -r requirements_pi.txt
```

> **numpy must stay < 2.** `picamera2`/`simplejpeg`/`ncnn`/`onnxruntime` are compiled
> against the numpy 1.x ABI; numpy 2.x triggers `numpy.dtype size changed` at import.
> The requirements pin `numpy<2` and `opencv-python<4.11` to prevent the resolver from
> pulling numpy 2.x back in. Note we use **full `opencv-python` (not -headless)** so
> `live_preview.py`'s `cv2.imshow` window works.

### Run
```bash
python3 main.py            # the deterrent
python3 live_preview.py    # diagnostic preview (run on the Pi desktop / VNC)
```

---

## 8. Tuning (`config.py`)

- `BUZZER_CONFIDENCE_THRESHOLD` — raise toward 0.90 for fewer false alarms, lower
  toward 0.80 to catch more.
- `ULTRASONIC_MIN_HZ` / `MAX_HZ` / `GLIDE_HZ` / `STEP_MS` — deterrent tone behaviour.
- `CONFIDENCE_THRESHOLD` / `IOU_THRESHOLD` — detector sensitivity.
- `MAX_CPU_TEMP_C` — lower for a more conservative thermal limit.
- `IMAGE_SIZE` — 320 = cooler/faster, 640 = more accurate/hotter.
- `ENGINE` — `"ncnn"` (default, fastest on Pi) or `"onnx"`.

---

## 9. Run on boot (systemd)

```bash
sudo tee /etc/systemd/system/monkey.service > /dev/null <<'EOF'
[Unit]
Description=Monkey Deterrent
After=multi-user.target pigpiod.service
Requires=pigpiod.service

[Service]
Type=simple
User=bobby
WorkingDirectory=/home/bobby/iotmonkeyalert-model/monkey_deterrent
Environment=TELEGRAM_BOT_TOKEN=123456:ABC-...
Environment=TELEGRAM_CHAT_ID=000000000
ExecStart=/home/bobby/iotmonkeyalert-model/monkey_deterrent/venv/bin/python3 main.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now monkey.service
```
