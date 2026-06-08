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

import cv2
import RPi.GPIO as GPIO
from picamera2 import Picamera2

import config
from buzzer import Buzzer
from detector_factory import build_detector
from thermal import cpu_temp_c, wait_until_cool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── GPIO setup ────────────────────────────────────────────────────────────────

def init_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(config.PIR_PIN, GPIO.IN)


def cleanup(buzzer: Buzzer, cam: Picamera2):
    log.info("Shutting down …")
    buzzer.cleanup()
    try:
        cam.stop()
    except Exception:
        pass
    GPIO.cleanup()


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


# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    log.info("Initialising GPIO …")
    init_gpio()

    log.info("Loading detector (engine=%s)", config.ENGINE)
    detector = build_detector()

    log.info("Starting camera …")
    cam = build_camera()

    buzzer = Buzzer(config.BUZZER_PIN)
    buzzer.short_beep(freq=1500, ms=200)   # startup beep

    last_alarm_time = 0.0

    def _shutdown(sig, frame):
        cleanup(buzzer, cam)
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
            if not GPIO.input(config.PIR_PIN):
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
            log.info(
                "Monkey detected! %d box(es), best conf=%.2f",
                len(detections), max(scores),
            )

            # ── Cooldown guard ───────────────────────────────────────────
            if now - last_alarm_time < config.DETECTION_COOLDOWN:
                remaining = config.DETECTION_COOLDOWN - (now - last_alarm_time)
                log.debug("Cooldown — %.0f s remaining", remaining)
                time.sleep(config.PIR_POLL_INTERVAL)
                continue

            last_alarm_time = now
            log.info("Sounding alarm for %.1f s …", config.BUZZER_DURATION)
            buzzer.sound_alarm(config.BUZZER_DURATION)

    except Exception as exc:
        log.exception("Unexpected error: %s", exc)
    finally:
        cleanup(buzzer, cam)


if __name__ == "__main__":
    run()
