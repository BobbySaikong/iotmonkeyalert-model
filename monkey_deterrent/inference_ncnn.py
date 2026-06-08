"""
NCNN inference wrapper — drop-in replacement for MonkeyDetector (inference.py).
Same YOLOv5 postprocessing, but uses Tencent's NCNN engine (faster on ARM CPU).

Requires:  pip install ncnn   (on the Pi)
Model files (from pnnx, committed via GitHub):
    <name>.ncnn.param
    <name>.ncnn.bin

pnnx names the I/O blobs "in0" (input) and "out0" (the decoded YOLOv5 output).
If your .param uses different names, set them via INPUT_BLOB / OUTPUT_BLOB below
or pass them to the constructor. Check the .param file: the input blob is on the
"Input" layer line, the final output is the last blob name.
"""

import numpy as np
import cv2
import ncnn


class MonkeyDetectorNCNN:
    def __init__(self, param_path: str, bin_path: str, img_size: int,
                 conf: float, iou: float,
                 input_blob: str = "in0", output_blob: str = "out0",
                 num_threads: int = 4):
        self.img_size = img_size
        self.conf_thresh = conf
        self.iou_thresh = iou
        self.input_blob = input_blob
        self.output_blob = output_blob

        self.net = ncnn.Net()
        self.net.opt.num_threads = num_threads
        self.net.opt.use_vulkan_compute = False   # Pi 4 has no usable Vulkan; CPU only
        self.net.load_param(param_path)
        self.net.load_model(bin_path)

    def preprocess(self, frame_rgb: np.ndarray):
        """Letterbox to img_size (top-left, pad 114). Returns ncnn.Mat + scale + orig wh."""
        h0, w0 = frame_rgb.shape[:2]
        scale = self.img_size / max(h0, w0)
        nh, nw = int(h0 * scale), int(w0 * scale)
        resized = cv2.resize(frame_rgb, (nw, nh), interpolation=cv2.INTER_LINEAR)

        canvas = np.full((self.img_size, self.img_size, 3), 114, dtype=np.uint8)
        canvas[:nh, :nw] = resized

        # ncnn.Mat from RGB; normalize to 0..1 (same as ONNX path: /255)
        mat = ncnn.Mat.from_pixels(
            canvas.tobytes(), ncnn.Mat.PixelType.PIXEL_RGB,
            self.img_size, self.img_size,
        )
        mat.substract_mean_normalize([0.0, 0.0, 0.0], [1 / 255.0, 1 / 255.0, 1 / 255.0])
        return mat, scale, (w0, h0)

    def postprocess(self, preds: np.ndarray, orig_wh, scale: float):
        """preds: [N, 5+C] YOLOv5 rows [cx,cy,w,h,obj,cls...] in img_size coords."""
        if preds.ndim == 1:
            preds = preds.reshape(-1, preds.shape[-1])
        boxes_cxcy = preds[:, :4]
        objectness = preds[:, 4]
        class_probs = preds[:, 5:]
        class_scores = objectness * class_probs.max(axis=1)

        mask = class_scores > self.conf_thresh
        if not mask.any():
            return []
        boxes_cxcy = boxes_cxcy[mask]
        class_scores = class_scores[mask]

        x1 = boxes_cxcy[:, 0] - boxes_cxcy[:, 2] / 2
        y1 = boxes_cxcy[:, 1] - boxes_cxcy[:, 3] / 2
        x2 = boxes_cxcy[:, 0] + boxes_cxcy[:, 2] / 2
        y2 = boxes_cxcy[:, 1] + boxes_cxcy[:, 3] / 2

        inv = 1.0 / scale
        x1 *= inv; y1 *= inv; x2 *= inv; y2 *= inv

        boxes_list = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1).tolist()
        scores_list = class_scores.tolist()
        indices = cv2.dnn.NMSBoxes(boxes_list, scores_list, self.conf_thresh, self.iou_thresh)
        if len(indices) == 0:
            return []

        ow, oh = orig_wh
        results = []
        for i in np.array(indices).flatten():
            bx, by, bw, bh = boxes_list[i]
            results.append((max(0, int(bx)), max(0, int(by)),
                            min(ow, int(bx + bw)), min(oh, int(by + bh)),
                            scores_list[i]))
        return results

    def detect(self, frame_rgb: np.ndarray):
        mat, scale, orig_wh = self.preprocess(frame_rgb)
        ex = self.net.create_extractor()
        ex.input(self.input_blob, mat)
        ret, out = ex.extract(self.output_blob)
        preds = np.array(out)               # shape [N, 5+C]
        return self.postprocess(preds, orig_wh, scale)
