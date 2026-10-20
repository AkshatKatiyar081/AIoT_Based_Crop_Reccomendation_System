import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
BASE_DIR = BACKEND_DIR.parent
ENV_PATH = BACKEND_DIR / ".env"

if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


# ─── Flask ────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key")
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "crop_recommendation.db"))
PORT = int(os.getenv("PORT", "5000"))

# ─── MQTT ─────────────────────────────────────────────────
# Defaults to the free public HiveMQ broker (no account needed).
# Use a unique MQTT_TOPIC_PREFIX so other people's messages don't mix with yours.
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "broker.hivemq.com")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "kisanmitra/demo").rstrip("/")
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "kisanmitra-backend")

TOPIC_SENSOR = f"{MQTT_TOPIC_PREFIX}/sensor"   # ESP32 -> backend
TOPIC_PUMP = f"{MQTT_TOPIC_PREFIX}/pump"       # backend -> ESP32

# Sensor data older than this is treated as offline
SENSOR_STALE_SECONDS = 15

# ─── Data and model paths ─────────────────────────────────
CROP_MODEL_PATH = BASE_DIR / "models" / "pune_crop_model.joblib"
CROP_METRICS_PATH = BASE_DIR / "models" / "pune_crop_metrics.json"
FERTILIZER_MODEL_PATH = BASE_DIR / "models" / "pune_fertilizer_model.joblib"
FERTILIZER_METRICS_PATH = BASE_DIR / "models" / "pune_fertilizer_metrics.json"
PROCESSED_SAMPLES_PATH = BASE_DIR / "data" / "processed" / "pune_soil_samples.csv"
GIPE_DIR = BASE_DIR / "data" / "gipe_maharashtra"
