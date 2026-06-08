# GPIO pin numbers (BCM mode)
PIR_PIN    = 17   # PIR sensor signal wire → GPIO17
BUZZER_PIN = 18   # Passive buzzer IN → GPIO18

# Model
ENGINE = "ncnn"   # "ncnn" (faster on Pi) or "onnx"

# ONNX paths (used when ENGINE == "onnx")
MODEL_PATH = "/home/bobby/iotmonkeyalert-model/macaque30epochs.onnx"

# NCNN paths (used when ENGINE == "ncnn") — from pnnx, pulled via GitHub
NCNN_PARAM = "/home/bobby/iotmonkeyalert-model/macaque30epochs.ncnn.param"
NCNN_BIN   = "/home/bobby/iotmonkeyalert-model/macaque30epochs.ncnn.bin"
NCNN_INPUT_BLOB  = "in0"    # confirm against the .param file
NCNN_OUTPUT_BLOB = "out0"   # confirm against the .param file

IMAGE_SIZE          = 416   # 416 is faster/cooler than 640; good enough for Pi
CONFIDENCE_THRESHOLD = 0.50
IOU_THRESHOLD        = 0.45

# Thermal safety
MAX_CPU_TEMP_C = 78.0   # pause inference above this to protect the SoC
TEMP_CHECK_INTERVAL = 5  # seconds between temperature polls when throttling

# Timing
DETECTION_COOLDOWN   = 15.0  # seconds between alarm triggers
BUZZER_DURATION      = 4.0   # seconds the alarm runs
PIR_POLL_INTERVAL    = 0.05  # seconds between PIR reads when idle

# Camera
CAMERA_WIDTH  = 640
CAMERA_HEIGHT = 480
