"""
Shared test setup: runs the backend offline against a throw-away database.

Import this module before any backend module. It
  - points DATABASE_PATH at a temporary file,
  - blanks the data.gov.in key so no live price request is made,
  - replaces the Open-Meteo call with a fixed forecast (FAKE_WEATHER).
"""

import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
_tmp = tempfile.mkdtemp(prefix="kisanmitra-test-")
os.environ["DATABASE_PATH"] = os.path.join(_tmp, "test.db")
os.environ["DATA_GOV_IN_API_KEY"] = ""          # config.py only fills unset keys from .env
os.environ["SECRET_KEY"] = "test-secret"
sys.path.insert(0, str(BACKEND))

import weather  # noqa: E402

FAKE_WEATHER = {
    "available": True, "taluka": "Haveli", "temperature_c": 26.0, "humidity_pct": 60,
    "precipitation_now_mm": 0.0, "rain_next_24h_mm": 0.0,
    "forecast": [{"date": "2026-11-01", "rain_mm": 0.0, "t_max": 30, "t_min": 16}] * 3,
    "source": "test stub",
}
weather.get_weather = lambda taluka: dict(FAKE_WEATHER, taluka=taluka)

import database  # noqa: E402

database.create_tables()

# A real Pune soil card (Haveli, medium N, low P, medium K) used across tests
SOIL = {"pH": 7.6, "OC": 0.55, "N": 230, "P": 18, "K": 180, "S": 12,
        "Zn": 0.7, "B": 0.6, "Fe": 5, "Mn": 3, "Cu": 0.3}
