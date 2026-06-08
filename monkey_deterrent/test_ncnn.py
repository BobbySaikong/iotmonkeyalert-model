#!/usr/bin/env python3
"""
NCNN smoke test — exercises the configured engine via the factory.

Unlike test_detect.py (which hardcodes the ONNX detector), this loads whatever
config.ENGINE selects, so it actually validates the ncnn .param/.bin wiring.

It tries the Pi camera; if unavailable it falls back to a synthetic frame so
the model still loads + runs (verifies blobs, shapes, postprocess) anywhere.

Usage:
    python test_ncnn.py            # 5 frames, 1s apart
    python test_ncnn.py 20 0.5     # 20 frames, 0.5s apart
"""
import os, sys, time, glob
import cv2
import numpy as np

import config
from detector_factory import build_detector
from thermal import cpu_temp_c

N   = int(sys.argv[1]) if len(sys.argv) > 1 else 5
GAP = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0

os.makedirs("snapshots", exist_ok=True)
for f in glob.glob("snapshots/*.jpg"):
    os.remove(f)

print(f"Engine: {config.ENGINE}")
print("Loading detector via factory ...")
det = build_detector()
print("Detector loaded OK.")

cam = None
try:
    from picamera2 import Picamera2
    cam = Picamera2()
    cfg = cam.create_preview_configuration(
        main={"size": (config.CAMERA_WIDTH, config.CAMERA_HEIGHT), "format": "RGB888"}
    )
    cam.configure(cfg)
    cam.start()
    time.sleep(1.5)
    print("Camera started.")
except Exception as e:
    print(f"No camera ({e}). Using synthetic frames.")

def get_frame():
    """Returns a true-RGB uint8 frame. picamera2 'RGB888' actually gives BGR, so flip it."""
    if cam is not None:
        return cv2.cvtColor(cam.capture_array(), cv2.COLOR_BGR2RGB)
    return np.random.randint(0, 255, (config.CAMERA_HEIGHT, config.CAMERA_WIDTH, 3), dtype=np.uint8)

print(f"Running {N} frame(s). CPU {cpu_temp_c():.1f}C\n")
try:
    for i in range(N):
        frame = get_frame()
        t = time.time()
        dets = det.detect(frame)
        dt = (time.time() - t) * 1000

        bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        for (x1, y1, x2, y2, score) in dets:
            cv2.rectangle(bgr, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(bgr, f"monkey {score:.2f}", (x1, max(0, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        out = f"snapshots/frame_{i:02d}.jpg"
        cv2.imwrite(out, bgr)
        best = max((d[4] for d in dets), default=0.0)
        print(f"[{i:02d}] {len(dets)} detection(s)  best={best:.2f}  "
              f"infer={dt:.0f}ms  CPU={cpu_temp_c():.1f}C  -> {out}")
        time.sleep(GAP)
finally:
    if cam is not None:
        cam.stop()
    print("\nDone. View: ls snapshots/")
