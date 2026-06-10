# Monkey Deterrent System — Raspberry Pi 4B

PIR-gated camera + ONNX monkey detection + passive buzzer alarm, with thermal throttling.

## Why your code crashed with "Illegal instruction"

The pip-installable `ultralytics` / `yolov8s` pull in a **PyTorch** build compiled for
desktop x86 CPUs. On the Pi's ARM (aarch64) CPU that triggers `Illegal instruction (SIGILL)`.

**Fix:** never run PyTorch/ultralytics on the Pi. Instead:
- Convert your `.pt` model to **ONNX on your laptop** (`convert_model.py`).
- Run inference on the Pi with **onnxruntime** only (`inference.py`) — no PyTorch needed.

## Wiring (BCM pin numbers)

| Component       | Pi pin            | Notes                                   |
|-----------------|-------------------|-----------------------------------------|
| PIR signal      | GPIO17 (pin 11)   | VCC→5V, GND→GND                         |
| Passive buzzer  | GPIO18 (pin 12)   | PWM-capable pin (passive buzzer needs PWM) |
| Pi Camera 2     | CSI ribbon port   | enable with `sudo raspi-config`         |

## Step 1 — On your LAPTOP: convert the model

```bash
pip install -r requirements_laptop.txt
python convert_model.py --weights macaque30epochs.pt --size 416
scp macaque.onnx bobby@<pi-ip>:/home/bobby/monkey_deterrent/macaque.onnx
```

## Step 2 — On the Pi: install deps

Recommended in a venv to avoid system conflicts:

```bash
cd /home/bobby/monkey_deterrent
python3 -m venv --system-site-packages venv   # inherits apt picamera2
source venv/bin/activate
pip install -r requirements_pi.txt
```

(`--system-site-packages` lets the venv see the apt-installed `picamera2`.)

## Step 3 — Run

```bash
python3 main.py
```

## Telegram alerts (optional)

When a monkey is detected **at or above `BUZZER_CONFIDENCE_THRESHOLD`** (default 0.85),
the system sounds the deterrent *and* sends an annotated photo (bounding box + confidence)
to your Telegram chat, captioned with the timestamp and detection rate. The photo is
encoded in memory and sent on a background thread — nothing is written to the SD card and
the deterrent loop is never blocked. If the credentials are unset, alerts are simply
disabled and everything else runs normally.

### Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the **token**.
2. Send your bot any message, then find your **chat_id**:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/getUpdates"
   ```
   Look for `"chat":{"id":<NUMBER>}` in the response.
3. Provide both as environment variables (kept out of git):
   ```bash
   export TELEGRAM_BOT_TOKEN="123456:ABC-..."
   export TELEGRAM_CHAT_ID="<NUMBER>"
   python3 main.py
   ```

Tune `BUZZER_CONFIDENCE_THRESHOLD` in `config.py` to control how confident a detection
must be before the buzzer fires and an alert is sent.

## Overheating prevention (built in)

1. **PIR gating** — camera frames are only inferred when the PIR detects motion.
   Idle = near-zero CPU, so the Pi stays cool most of the time.
2. **imgsz 416 + 10 fps + 2 inference threads** — keeps load (and heat) down.
3. **Thermal throttle** (`thermal.py`) — if the SoC hits 78°C, inference pauses
   until it drops to 73°C (5°C hysteresis).
4. **Detection cooldown** — 15 s between alarms avoids redundant inference bursts.

**Hardware recommendation:** add a small heatsink + fan or the official Pi 4 case fan.
Under sustained sun a passive heatsink alone may not be enough.

Check temperature anytime:
```bash
vcgencmd measure_temp
```

## Tuning (edit `config.py`)

- `CONFIDENCE_THRESHOLD` — raise to reduce false alarms.
- `MAX_CPU_TEMP_C` — lower for a more conservative thermal limit.
- `IMAGE_SIZE` — 320 = cooler/faster, 640 = more accurate/hotter.

## Run on boot (optional)

```bash
sudo tee /etc/systemd/system/monkey.service > /dev/null <<'EOF'
[Unit]
Description=Monkey Deterrent
After=multi-user.target

[Service]
Type=simple
User=bobby
WorkingDirectory=/home/bobby/monkey_deterrent
Environment=TELEGRAM_BOT_TOKEN=123456:ABC-...
Environment=TELEGRAM_CHAT_ID=000000000
ExecStart=/home/bobby/monkey_deterrent/venv/bin/python3 main.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now monkey.service
```
