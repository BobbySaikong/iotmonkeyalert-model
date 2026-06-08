"""
Returns the configured detector (NCNN or ONNX). Both expose the same
.detect(frame_rgb) -> [(x1,y1,x2,y2,score), ...] interface.
"""
import config


def build_detector():
    if config.ENGINE == "ncnn":
        from inference_ncnn import MonkeyDetectorNCNN
        return MonkeyDetectorNCNN(
            param_path=config.NCNN_PARAM,
            bin_path=config.NCNN_BIN,
            img_size=config.IMAGE_SIZE,
            conf=config.CONFIDENCE_THRESHOLD,
            iou=config.IOU_THRESHOLD,
            input_blob=config.NCNN_INPUT_BLOB,
            output_blob=config.NCNN_OUTPUT_BLOB,
        )
    elif config.ENGINE == "onnx":
        from inference import MonkeyDetector
        return MonkeyDetector(
            model_path=config.MODEL_PATH,
            img_size=config.IMAGE_SIZE,
            conf=config.CONFIDENCE_THRESHOLD,
            iou=config.IOU_THRESHOLD,
        )
    raise ValueError(f"Unknown ENGINE: {config.ENGINE!r} (use 'ncnn' or 'onnx')")
