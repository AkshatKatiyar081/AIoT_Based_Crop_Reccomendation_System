"""
Live weather for a Pune taluka from Open-Meteo (free, no API key).
Results are cached for 10 minutes so the dashboard and simulator don't spam the API.
"""

import json
import threading
import time
import urllib.parse
import urllib.request

from knowledge import TALUKAS

API_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_SECONDS = 600

# Rough monthly normals for Pune, used only if the API can't be reached
PUNE_NORMALS = {  # month: (temperature °C, humidity %)
    1: (21, 45), 2: (23, 38), 3: (26, 33), 4: (29, 35), 5: (29, 48), 6: (27, 72),
    7: (25, 82), 8: (24, 83), 9: (25, 78), 10: (25, 63), 11: (22, 52), 12: (21, 48),
}

_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def get_weather(taluka: str) -> dict:
    loc = TALUKAS.get(taluka) or TALUKAS["Haveli"]
    key = taluka if taluka in TALUKAS else "Haveli"

    with _lock:
        cached = _cache.get(key)
        if cached and time.time() - cached[0] < CACHE_SECONDS:
            return cached[1]

    params = {
        "latitude": loc["lat"], "longitude": loc["lon"],
        "current": "temperature_2m,relative_humidity_2m,precipitation",
        "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
        "forecast_days": 3, "timezone": "Asia/Kolkata",
    }
    try:
        url = f"{API_URL}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        daily = data["daily"]
        result = {
            "available": True,
            "taluka": key,
            "temperature_c": data["current"]["temperature_2m"],
            "humidity_pct": data["current"]["relative_humidity_2m"],
            "precipitation_now_mm": data["current"]["precipitation"],
            "rain_next_24h_mm": round(daily["precipitation_sum"][0] or 0, 1),
            "forecast": [
                {"date": d, "rain_mm": r, "t_max": hi, "t_min": lo}
                for d, r, hi, lo in zip(daily["time"], daily["precipitation_sum"],
                                        daily["temperature_2m_max"], daily["temperature_2m_min"])
            ],
            "source": "Open-Meteo",
        }
    except Exception as e:
        month = time.localtime().tm_mon
        t, h = PUNE_NORMALS[month]
        result = {
            "available": False, "taluka": key, "temperature_c": t, "humidity_pct": h,
            "precipitation_now_mm": 0.0, "rain_next_24h_mm": 0.0, "forecast": [],
            "source": f"Pune monthly normals (Open-Meteo unreachable: {e.__class__.__name__})",
        }

    with _lock:
        _cache[key] = (time.time(), result)
    return result
