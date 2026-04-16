import os
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
ENV_PATH = Path(__file__).resolve().parent / ".env"

if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _get_env_list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


# ─── Flask ────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key")
DATABASE_PATH = os.path.join(BASE_DIR, "crop_recommendation.db")

# ─── Gemini AI ────────────────────────────────────────────
GEMINI_API_KEYS = _get_env_list("GEMINI_API_KEYS")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ─── HiveMQ Cloud MQTT ────────────────────────────────────
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "8883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "farm/sensor/data")
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "crop-backend-subscriber")

# ─── ML Model paths ───────────────────────────────────────
MODEL_PATH  = os.path.join(BASE_DIR, "crop_model.joblib")
SCALER_PATH = os.path.join(BASE_DIR, "scaler.joblib")

# ─── Sensor simulation ranges (fallback) ──────────────────
SENSOR_RANGES = {
    "N":           (0,   140),
    "P":           (5,   145),
    "K":           (5,   205),
    "temperature": (8,   44),
    "humidity":    (14,  100),
    "ph":          (3.5, 10),
    "rainfall":    (20,  300),
}
