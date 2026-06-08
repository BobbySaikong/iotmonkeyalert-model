"""
Run this script on your LAPTOP.

ONNX export (from .pt):
    pip install ultralytics onnx onnxsim
    python convert_model.py --weights macaque30epochs.pt --size 416

NCNN export (from the EXISTING .onnx — recommended, keeps the YOLOv5 output format
that the Pi inference code already handles):
    pip install pnnx
    python convert_model.py --onnx2ncnn macaque30epochs.onnx --size 416

That produces:
    macaque30epochs.ncnn.param   (network structure)
    macaque30epochs.ncnn.bin     (weights)

Then commit both to your GitHub repo and `git pull` on the Pi.
"""

import argparse
from pathlib import Path

def onnx_to_ncnn(onnx_path: Path, size: int):
    """Convert an existing ONNX model to NCNN using pnnx (pip install pnnx)."""
    if not onnx_path.exists():
        raise FileNotFoundError(f"ONNX not found: {onnx_path}")
    print(f"Converting {onnx_path} -> NCNN via pnnx (inputshape=[1,3,{size},{size}]) ...")
    import subprocess
    # pnnx writes <stem>.ncnn.param / <stem>.ncnn.bin next to the input
    cmd = ["pnnx", str(onnx_path), f"inputshape=[1,3,{size},{size}]"]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    stem = onnx_path.with_suffix("")  # drop .onnx
    print("\nDone! Outputs:")
    print(f"  {stem}.ncnn.param")
    print(f"  {stem}.ncnn.bin")
    print("\nCommit BOTH files to GitHub, then on the Pi: git pull")
    print("pnnx also emits *_pnnx.py and debug files — you can ignore/gitignore those.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", default="macaque30epochs.pt", help="Path to .pt file (ONNX export)")
    parser.add_argument("--onnx2ncnn", default=None, help="Path to existing .onnx -> convert to NCNN")
    parser.add_argument("--size", type=int, default=416, help="Inference image size (416 or 640)")
    args = parser.parse_args()

    if args.onnx2ncnn:
        onnx_to_ncnn(Path(args.onnx2ncnn), args.size)
        return

    weights = Path(args.weights)
    if not weights.exists():
        raise FileNotFoundError(f"Model not found: {weights}")

    print(f"Loading {weights} ...")
    from ultralytics import YOLO
    model = YOLO(str(weights))

    print(f"Exporting to ONNX (imgsz={args.size}, opset=12, simplify=True) ...")
    model.export(
        format="onnx",
        imgsz=args.size,
        opset=12,          # ONNX Runtime on Pi works best with opset ≤12
        simplify=True,     # onnxsim pass — removes redundant nodes
        dynamic=False,     # fixed batch size = faster on Pi
        half=False,        # Pi CPU does not support FP16 ONNX
    )

    onnx_path = weights.with_suffix(".onnx")
    print(f"\nDone! Output: {onnx_path}")
    print(f"\nCopy to Pi:")
    print(f"  scp {onnx_path} bobby@<pi-ip>:/home/bobby/monkey_deterrent/macaque.onnx")
    print("\nOptional — also export NCNN (faster on Pi CPU):")
    print("  model.export(format='ncnn', imgsz=416)")

if __name__ == "__main__":
    main()
