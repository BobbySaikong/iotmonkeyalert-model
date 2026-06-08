"""
Passive buzzer controller — generates deterrent sound patterns via GPIO PWM.
A passive buzzer needs a PWM signal (unlike an active buzzer).
"""

import time
import RPi.GPIO as GPIO


class Buzzer:
    def __init__(self, pin: int):
        self.pin = pin
        GPIO.setup(pin, GPIO.OUT)
        self._pwm = GPIO.PWM(pin, 1000)
        self._active = False

    def _sweep(self, freqs, step_time: float):
        for f in freqs:
            self._pwm.ChangeFrequency(f)
            time.sleep(step_time)

    def sound_alarm(self, duration: float = 4.0):
        """Multi-tone sweep — more effective as a deterrent than a flat tone."""
        self._pwm.start(50)   # 50% duty cycle
        self._active = True
        end = time.time() + duration
        pattern = [2000, 3000, 4000, 3000, 1500, 2500, 4000, 1000]
        while time.time() < end:
            self._sweep(pattern, step_time=0.15)
        self._pwm.stop()
        self._active = False

    def short_beep(self, freq: int = 2000, ms: int = 200):
        """Single short beep for status feedback."""
        self._pwm.start(50)
        self._pwm.ChangeFrequency(freq)
        time.sleep(ms / 1000.0)
        self._pwm.stop()

    def cleanup(self):
        if self._active:
            self._pwm.stop()
