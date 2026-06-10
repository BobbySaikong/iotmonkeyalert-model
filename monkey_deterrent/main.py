#!/usr/bin/env python3
"""
Monkey Deterrent System — Raspberry Pi 4B
Hardware: PIR sensor (GPIO17), Passive buzzer (GPIO18), Pi Camera Module 2

Flow:
  PIR idle  → poll every 50 ms, camera off, inference off  → minimal heat
  PIR high  → capture frame → ONNX detect → monkey? → sound alarm
  Temp > 78°C → pause inference until cooled
"""

import logging
import signal
import sys
import time
from datetime import datetime

import cv2
import pigpio
from picamera2 import Picamera2

import config
from buzzer import Buzzer
from detector_factory import build_detector
from telegram_notifier import TelegramNotifier
from thermal import cpu_temp_c, wait_until_cool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── GPIO setup ────────────────────────────────────────────────────────────────

def init_gpio() -> pigpio.pi:
    pi = pigpio.pi()   # connects to the local pigpiod daemon
    if not pi.connected:
        raise RuntimeError(
            "Cannot connect to pigpiod. Start it with: "
            "sudo systemctl enable --now pigpiod"
        )
    pi.set_mode(config.PIR_PIN, pigpio.INPUT)

    # Silent idle state for the transducer IN pin. This module airhorns when IN
    # is held at a steady level (DC) while powered, but is silent when IN floats.
    # So idle = high-Z INPUT (no pull) — same as leaving the IN wire unplugged.
    pi.hardware_PWM(config.BUZZER_PIN, 0, 0)
    pi.set_mode(config.BUZZER_PIN, pigpio.INPUT)
    pi.set_pull_up_down(config.BUZZER_PIN, pigpio.PUD_OFF)
    return pi


def cleanup(pi: pigpio.pi, buzzer: Buzzer, cam: Picamera2):
    log.info("Shutting down …")
    buzzer.cleanup()
    try:
        cam.stop()
    except Exception:
        pass
    if pi.connected:
        pi.hardware_PWM(config.BUZZER_PIN, 0, 0)
        pi.set_mode(config.BUZZER_PIN, pigpio.INPUT)   # release to high-Z = silent
        pi.set_pull_up_down(config.BUZZER_PIN, pigpio.PUD_OFF)
        pi.stop()


# ── Camera ────────────────────────────────────────────────────────────────────

def build_camera() -> Picamera2:
    cam = Picamera2()
    cfg = cam.create_preview_configuration(
        main={
            "size": (config.CAMERA_WIDTH, config.CAMERA_HEIGHT),
            "format": "RGB888",
        },
        controls={"FrameRate": 10},   # 10 fps is plenty; lower FPS = less heat
    )
    cam.configure(cfg)
    cam.start()
    time.sleep(1.0)   # let AWB settle
    return cam


# ── Annotation ────────────────────────────────────────────────────────────────

def annotate_frame(frame_bgr, detections):
    """Draw detection boxes + confidence labels on a copy of the BGR frame."""
    annotated = frame_bgr.copy()
    for x1, y1, x2, y2, score in detections:
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
        label = f"monkey {score:.0%}"
        cv2.putText(
            annotated, label, (x1, max(0, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2,
        )
    return annotated


# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    log.info("Initialising GPIO (pigpio) …")
    pi = init_gpio()

    log.info("Loading detector (engine=%s)", config.ENGINE)
    detector = build_detector()

    log.info("Starting camera …")
    cam = build_camera()

    buzzer = Buzzer(pi, config.BUZZER_PIN)
    buzzer.short_beep(ms=200)   # startup ultrasonic blip

    notifier = TelegramNotifier(
        config.TELEGRAM_BOT_TOKEN,
        config.TELEGRAM_CHAT_ID,
        config.TELEGRAM_TIMEOUT,
    )

    last_alarm_time = 0.0

    def _shutdown(sig, frame):
        cleanup(pi, buzzer, cam)
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info("System ready — watching for monkeys …")

    try:
        while True:
            # ── Thermal throttle ─────────────────────────────────────────
            temp = cpu_temp_c()
            if temp >= config.MAX_CPU_TEMP_C:
                wait_until_cool(config.MAX_CPU_TEMP_C, config.TEMP_CHECK_INTERVAL)

            # ── PIR gate — saves CPU when no motion ──────────────────────
            if not pi.read(config.PIR_PIN):
                time.sleep(config.PIR_POLL_INTERVAL)
                continue

            log.debug("PIR triggered — capturing frame (CPU %.1f°C)", temp)

            # ── Capture & infer ──────────────────────────────────────────
            # picamera2 "RGB888" returns BGR in the array; detector wants true RGB.
            frame = cam.capture_array()                    # BGR uint8 [H, W, 3]
            detections = detector.detect(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            if not detections:
                time.sleep(config.PIR_POLL_INTERVAL)
                continue

            now = time.time()
            scores = [d[4] for d in detections]
            best = max(scores)
            log.info(
                "Monkey detected! %d box(es), best conf=%.2f",
                len(detections), best,
            )

            # ── Confidence gate — only high-confidence hits sound the alarm ─
            if best < config.BUZZER_CONFIDENCE_THRESHOLD:
                log.info(
                    "Below buzzer threshold (%.2f < %.2f) — no alarm.",
                    best, config.BUZZER_CONFIDENCE_THRESHOLD,
                )
                time.sleep(config.PIR_POLL_INTERVAL)
                continue

            # ── Cooldown guard ───────────────────────────────────────────
            if now - last_alarm_time < config.DETECTION_COOLDOWN:
                remaining = config.DETECTION_COOLDOWN - (now - last_alarm_time)
                log.debug("Cooldown — %.0f s remaining", remaining)
                time.sleep(config.PIR_POLL_INTERVAL)
                continue

            last_alarm_time = now

            # ── Telegram alert — annotated photo, encoded in memory ──────
            annotated = annotate_frame(frame, detections)
            ok, buf = cv2.imencode(".jpg", annotated)
            if ok:
                caption = (
                    "🐒 Monkey detected\n"
                    f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                    f"Detection rate: {best:.0%} ({len(detections)} box(es))"
                )
                notifier.send_photo_async(buf.tobytes(), caption)
            else:
                log.warning("JPEG encode failed — skipping Telegram alert.")

            log.info("Sounding alarm for %.1f s …", config.BUZZER_DURATION)
            buzzer.sound_alarm(config.BUZZER_DURATION)

    except Exception as exc:
        log.exception("Unexpected error: %s", exc)
    finally:
        cleanup(pi, buzzer, cam)


if __name__ == "__main__":
    run()
