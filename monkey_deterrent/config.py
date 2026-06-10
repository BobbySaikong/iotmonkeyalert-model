import os

# GPIO pin numbers (BCM mode)
PIR_PIN    = 17   # PIR sensor signal wire → GPIO17
BUZZER_PIN = 18   # Ultrasonic transducer IN → GPIO18 (PWM0 hardware channel)

# Ultrasonic deterrent — randomized frequency sweep (Hz)
# GPIO18 is a hardware-PWM pin, so pigpio drives these cleanly with no CPU jitter.
ULTRASONIC_MIN_HZ  = 20_000
ULTRASONIC_MAX_HZ  = 40_000
ULTRASONIC_DUTY    = 500_000 # pigpio duty cycle: 0–1_000_000 (500_000 = 50%)

# Smooth random-walk parameters — abrupt frequency jumps create audible clicks,
# so we glide between random targets in small ultrasonic steps (transient energy
# stays >20 kHz = inaudible).
ULTRASONIC_GLIDE_HZ   = 500    # Hz moved per micro-step while gliding
ULTRASONIC_GLIDE_MS   = 3      # dwell per micro-step
ULTRASONIC_STEP_MS    = 60     # dwell once a random target is reached

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

# The detector still *detects* from CONFIDENCE_THRESHOLD, but the buzzer (and the
# Telegram alert) only fire when the best detection in a frame is at/above this.
# Raise toward 0.90 for fewer false alarms; lower toward 0.80 to catch more.
BUZZER_CONFIDENCE_THRESHOLD = 0.85

# Telegram alerts — secrets come from the environment, never committed to git.
# Set these in the systemd unit (Environment=...) or your shell before running.
# Get the bot token from BotFather; get chat_id by messaging the bot then calling
#   https://api.telegram.org/bot<TOKEN>/getUpdates
# Leaving either blank disables alerts (the deterrent still runs normally).
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_TIMEOUT   = 10   # seconds for the sendPhoto HTTPS request

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
