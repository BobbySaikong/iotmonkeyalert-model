#!/usr/bin/env python3
"""
Headless camera + model test.
Captures N frames from the Pi camera, runs the monkey detector, and saves
annotated JPGs to ./snapshots/ so you can view them over SSH (scp them, or
open in a file browser).

Usage:
    python test_detect.py            # 5 frames, 1s apart
    python test_detect.py 20 0.5     # 20 frames, 0.5s apart
"""
import os, sys, time, glob
import cv2
import numpy as np
from picamera2 import Picamera2

import config
from inference import MonkeyDetector
from thermal import cpu_temp_c

MODEL = os.environ.get("MODEL", "/home/bobby/iotmonkeyalert-model/macaque30epochs.onnx")
N      = int(sys.argv[1]) if len(sys.argv) > 1 else 5
GAP    = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0

os.makedirs("snapshots", exist_ok=True)
for f in glob.glob("snapshots/*.jpg"):
    os.remove(f)

print(f"Loading model: {MODEL}")
det = MonkeyDetector(MODEL, config.IMAGE_SIZE, config.CONFIDENCE_THRESHOLD, config.IOU_THRESHOLD)

print("Starting camera ...")
cam = Picamera2()
cfg = cam.create_preview_configuration(
    main={"size": (config.CAMERA_WIDTH, config.CAMERA_HEIGHT), "format": "RGB888"}
)
cam.configure(cfg)
cam.start()
time.sleep(1.5)  # let exposure settle

print(f"Capturing {N} frames ({GAP}s apart). CPU {cpu_temp_c():.1f}C\n")
try:
    for i in range(N):
        # picamera2 "RGB888" actually returns BGR; flip to true RGB for the detector.
        frame = cv2.cvtColor(cam.capture_array(), cv2.COLOR_BGR2RGB)
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
    cam.stop()
    print(f"\nDone. View images:  ls snapshots/   then scp them to your laptop.")
