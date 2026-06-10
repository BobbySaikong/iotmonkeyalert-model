# Pi Session Hand-off — Confidence-gated buzzer + Telegram alerts

This file briefs a Claude Code session (or a human) running **on the Raspberry Pi**.
The code changes are already committed and pushed on branch
`claude/monkey-deterrent-alerts-hnglle`. Your job on the Pi is to pull, configure,
and verify them on real hardware.

## What changed (already in this branch)

- **`config.py`** — added `BUZZER_CONFIDENCE_THRESHOLD = 0.85` and Telegram settings read
  from env vars (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_TIMEOUT`).
- **`telegram_notifier.py`** (new) — `TelegramNotifier` posts an annotated detection photo to
  Telegram via `sendPhoto`, in memory (no SD-card write), on a background daemon thread; all
  errors are logged, never raised.
- **`main.py`** — confidence gate before the alarm (skip if `best < BUZZER_CONFIDENCE_THRESHOLD`);
  on a confirmed hit, annotate the frame, JPEG-encode in memory, send to Telegram with a
  timestamp + detection-rate caption, then sound the buzzer.
- **`requirements_pi.txt`** — added `requests>=2.31.0`.
- **`README.md`** — Telegram setup + systemd env vars.

## Step 1 — Pull the branch

```bash
cd ~/iotmonkeyalert-model
git fetch origin claude/monkey-deterrent-alerts-hnglle
git checkout claude/monkey-deterrent-alerts-hnglle
git pull origin claude/monkey-deterrent-alerts-hnglle
```

## Step 2 — Install the new dependency

```bash
cd ~/iotmonkeyalert-model/monkey_deterrent
source venv/bin/activate
pip install -r requirements_pi.txt   # picks up 'requests'
```

## Step 3 — Get a Telegram chat_id (one-time)

You need BOTH the BotFather token AND a chat_id (the destination).

1. Send your bot any message in Telegram.
2. Then:
   ```bash
   curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"
   ```
3. Read `"chat":{"id":<NUMBER>}` from the JSON — that number is your chat_id.

## Step 4 — Provide credentials (kept out of git)

For a quick run:
```bash
export TELEGRAM_BOT_TOKEN="123456:ABC-..."
export TELEGRAM_CHAT_ID="<NUMBER>"
```

For the systemd service, add to the `[Service]` block (see README):
```
Environment=TELEGRAM_BOT_TOKEN=123456:ABC-...
Environment=TELEGRAM_CHAT_ID=<NUMBER>
```
then `sudo systemctl daemon-reload && sudo systemctl restart monkey.service`.

## Step 5 — Smoke-test Telegram before the full run (optional but recommended)

Sends one of the existing snapshot images so you confirm credentials + network work,
independent of the camera/model:

```bash
cd ~/iotmonkeyalert-model/monkey_deterrent
python3 -c "
import cv2
from telegram_notifier import TelegramNotifier
import config
img = cv2.imread('snapshots/frame_00.jpg')
ok, buf = cv2.imencode('.jpg', img)
n = TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, config.TELEGRAM_TIMEOUT)
print('enabled:', n.enabled)
n._send(buf.tobytes(), 'Telegram test from Pi')   # synchronous for the test
"
```
Expect the photo to arrive in your Telegram chat. If `enabled` is `False`, the env
vars aren't set in this shell.

## Step 6 — Run the real thing

```bash
python3 main.py
```

Present a monkey image/video to the camera and confirm:
- The buzzer fires **only** when best confidence ≥ `BUZZER_CONFIDENCE_THRESHOLD` (0.85).
  Lower-confidence detections log `"Below buzzer threshold ..."` and stay silent.
- A Telegram photo arrives with red bounding box(es), a confidence label, and a caption
  showing the timestamp + detection rate.
- Alerts are rate-limited by the existing 15 s `DETECTION_COOLDOWN`.

## Tuning

- `BUZZER_CONFIDENCE_THRESHOLD` in `config.py` — raise toward 0.90 for fewer false alarms,
  lower toward 0.80 to catch more.
- Unset credentials = alerts disabled (logged warning); the deterrent still runs normally.

## Notes / gotchas

- The photo is encoded in RAM and sent on a background thread — no SD-card writes, and the
  network call never blocks the alarm or the loop.
- `picamera2` / `pigpio` are Pi-only; this code can only be run end-to-end on the Pi (the
  cloud session could only syntax-check it).
- Make sure `pigpiod` is running: `sudo systemctl enable --now pigpiod`.
