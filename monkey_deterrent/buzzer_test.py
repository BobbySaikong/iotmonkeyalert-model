#!/usr/bin/env python3
"""
Diagnostic for the buzzer/transducer on GPIO18.
Run:  python3 buzzer_test.py
Listen during each step and note what you hear.
"""
import time
import pigpio
import config

pi = pigpio.pi()
assert pi.connected, "pigpiod not running: sudo systemctl enable --now pigpiod"

PIN = config.BUZZER_PIN
DUTY = 500_000  # 50%

def silence():
    # Idle = high-Z INPUT (float). Holding IN at a steady level airhorns this
    # module; floating is silent (same as unplugging the IN wire).
    pi.hardware_PWM(PIN, 0, 0)
    pi.set_mode(PIN, pigpio.INPUT)
    pi.set_pull_up_down(PIN, pigpio.PUD_OFF)

def tone(hz, secs, label):
    print(f"  {label}: {hz} Hz for {secs}s")
    pi.hardware_PWM(PIN, hz, DUTY)
    time.sleep(secs)
    silence()
    time.sleep(0.5)

try:
    print("STEP 1 — steady audible 2 kHz (sanity: you SHOULD hear this):")
    tone(2_000, 2, "2kHz")

    print("STEP 2 — steady 30 kHz (ultrasonic: you should hear NOTHING):")
    tone(30_000, 3, "30kHz")

    print("STEP 3 — steady 40 kHz (ultrasonic: silent if transducer is real):")
    tone(40_000, 3, "40kHz")

    print("STEP 4 — idle (high-Z float): should be SILENT for 3s")
    silence()
    time.sleep(3)
finally:
    silence()
    pi.stop()
    print("done.")
