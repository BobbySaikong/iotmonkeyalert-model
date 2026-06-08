"""
Lightweight ONNX inference wrapper — no ultralytics, no PyTorch on the Pi.
Handles YOLOv8 output format: [1, 4+num_classes, 8400].
"""

import numpy as np
import cv2
import onnxruntime as ort


class MonkeyDetector:
    def __init__(self, model_path: str, img_size: int, conf: float, iou: float):
        self.img_size = img_size
        self.conf_thresh = conf
        self.iou_thresh = iou

        sess_opts = ort.SessionOptions()
        sess_opts.intra_op_num_threads = 2   # leave cores for system tasks
        sess_opts.inter_op_num_threads = 1
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.session = ort.InferenceSession(
            model_path,
            sess_options=sess_opts,
            providers=["CPUExecutionProvider"],
        )
        self.input_name  = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

    def preprocess(self, frame_rgb: np.ndarray) -> tuple[np.ndarray, float, float]:
        """Letterbox-resize, normalize → NCHW float32. Returns tensor + scale factors."""
        h0, w0 = frame_rgb.shape[:2]
        scale = self.img_size / max(h0, w0)
        nh, nw = int(h0 * scale), int(w0 * scale)
        resized = cv2.resize(frame_rgb, (nw, nh), interpolation=cv2.INTER_LINEAR)

        canvas = np.full((self.img_size, self.img_size, 3), 114, dtype=np.uint8)
        canvas[:nh, :nw] = resized

        tensor = canvas.astype(np.float32) / 255.0
        tensor = np.transpose(tensor, (2, 0, 1))[np.newaxis]   # → NCHW
        return tensor, scale, (w0, h0)

    def postprocess(self, raw: np.ndarray, orig_wh: tuple[int, int], scale: float):
        """
        raw: [1, N, 5+C]  (YOLOv5 decoded output0)
             row = [cx, cy, w, h, objectness, class0, class1, ...]
        Returns list of (x1, y1, x2, y2, score) in original image coords.
        """
        preds = raw[0]                       # → [N, 5+C], already sigmoid-decoded
        boxes_cxcy = preds[:, :4]            # cx,cy,w,h in img_size (416) coords
        objectness = preds[:, 4]
        class_probs = preds[:, 5:]
        # confidence = objectness * best class probability  (YOLOv5 convention)
        class_scores = objectness * class_probs.max(axis=1)

        mask = class_scores > self.conf_thresh
        if not mask.any():
            return []

        boxes_cxcy = boxes_cxcy[mask]
        class_scores = class_scores[mask]

        # cx,cy,w,h (in img_size coords) → x1,y1,x2,y2
        x1 = boxes_cxcy[:, 0] - boxes_cxcy[:, 2] / 2
        y1 = boxes_cxcy[:, 1] - boxes_cxcy[:, 3] / 2
        x2 = boxes_cxcy[:, 0] + boxes_cxcy[:, 2] / 2
        y2 = boxes_cxcy[:, 1] + boxes_cxcy[:, 3] / 2

        # Scale back to original image size
        inv = 1.0 / scale
        x1 *= inv; y1 *= inv; x2 *= inv; y2 *= inv

        boxes_list  = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1).tolist()
        scores_list = class_scores.tolist()

        indices = cv2.dnn.NMSBoxes(boxes_list, scores_list, self.conf_thresh, self.iou_thresh)
        if len(indices) == 0:
            return []

        results = []
        ow, oh = orig_wh
        for i in indices.flatten():
            bx, by, bw, bh = boxes_list[i]
            rx1 = max(0, int(bx))
            ry1 = max(0, int(by))
            rx2 = min(ow, int(bx + bw))
            ry2 = min(oh, int(by + bh))
            results.append((rx1, ry1, rx2, ry2, scores_list[i]))
        return results

    def detect(self, frame_rgb: np.ndarray):
        tensor, scale, orig_wh = self.preprocess(frame_rgb)
        raw = self.session.run([self.output_name], {self.input_name: tensor})[0]
        return self.postprocess(raw, orig_wh, scale)
