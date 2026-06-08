#!/usr/bin/env python3
"""
LIVE GUI preview — run this from the Pi DESKTOP (needs a display).
Shows the camera feed with monkey detection boxes drawn in real time.

Run from a desktop terminal:
    cd /home/bobby/monkey_deterrent
    source venv/bin/activate
    python live_preview.py

Controls:
    q  = quit
    s  = save current frame to snapshots/
"""
import os, time
import cv2
import numpy as np
from picamera2 import Picamera2

import config
from detector_factory import build_detector
from thermal import cpu_temp_c

os.makedirs("snapshots", exist_ok=True)

print(f"Loading {config.ENGINE} detector ...")
det = build_detector()

print("Starting camera ...")
cam = Picamera2()
cfg = cam.create_preview_configuration(
    main={"size": (config.CAMERA_WIDTH, config.CAMERA_HEIGHT), "format": "RGB888"}
)
cam.configure(cfg)
cam.start()
time.sleep(1.5)

print("Live preview running — press 'q' in the window to quit, 's' to save.")
win = "Monkey Detector (q=quit, s=save)"
cv2.namedWindow(win, cv2.WINDOW_NORMAL)

# Frame-skip: only run detection every Nth frame; reuse the last boxes in between.
# Higher N = smoother video but staler boxes. Override with: DETECT_EVERY=5 python live_preview.py
DETECT_EVERY = int(os.environ.get("DETECT_EVERY", "5"))

prev = time.time()
fps = 0.0
saved = 0
frame_i = 0
dets = []          # last known detections, reused on skipped frames
try:
    while True:
        # picamera2 "RGB888" actually returns BGR in the numpy array (OpenCV-ready).
        bgr = cam.capture_array()                   # already BGR — use directly for cv2

        if frame_i % DETECT_EVERY == 0:
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)  # detector expects true RGB
            dets = det.detect(rgb)
        frame_i += 1

        for (x1, y1, x2, y2, score) in dets:
            cv2.rectangle(bgr, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(bgr, f"monkey {score:.2f}", (x1, max(0, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        now = time.time()
        fps = 0.9 * fps + 0.1 * (1.0 / max(now - prev, 1e-3))
        prev = now
        hud = f"FPS {fps:4.1f} | CPU {cpu_temp_c():.1f}C | {len(dets)} det | 1/{DETECT_EVERY}"
        cv2.putText(bgr, hud, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        cv2.imshow(win, bgr)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        if key == ord('s'):
            out = f"snapshots/live_{saved:02d}.jpg"
            cv2.imwrite(out, bgr)
            print("saved", out)
            saved += 1
finally:
    cam.stop()
    cv2.destroyAllWindows()
    print("Stopped.")
