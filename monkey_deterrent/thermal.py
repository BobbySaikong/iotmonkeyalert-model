"""
Thermal monitor — reads the SoC temperature and throttles inference
so the Pi 4B does not overheat under continuous camera + inference load.
"""

import time
import logging

_TEMP_PATH = "/sys/class/thermal/thermal_zone0/temp"
log = logging.getLogger(__name__)


def cpu_temp_c() -> float:
    with open(_TEMP_PATH) as f:
        return int(f.read().strip()) / 1000.0


def wait_until_cool(max_temp: float, check_interval: float = 5.0):
    """Block until CPU temperature drops below max_temp."""
    temp = cpu_temp_c()
    if temp < max_temp:
        return
    log.warning("CPU %.1f°C ≥ %.1f°C — pausing inference to cool down", temp, max_temp)
    while True:
        time.sleep(check_interval)
        temp = cpu_temp_c()
        log.info("CPU temp: %.1f°C", temp)
        if temp < max_temp - 5.0:   # 5°C hysteresis so we don't ping-pong
            log.info("Resuming — CPU temp %.1f°C", temp)
            return
