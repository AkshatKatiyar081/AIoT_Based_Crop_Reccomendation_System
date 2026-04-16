"""
blynk_service.py — Push sensor data and recommendations to Blynk
"""
import os
import requests
import threading
from datetime import datetime
import time

# ── Configure Blynk token through environment variables ─────────────────────
BLYNK_TOKEN = os.getenv("BLYNK_TOKEN", "")
BLYNK_BASE  = "https://blynk.cloud/external/api"
_last_sensor_push_ts = 0.0
SENSOR_PUSH_MIN_INTERVAL = 0.8  # Allow push every 0.8 seconds for live updates


def _push(pin: str, value) -> None:
    """Push one virtual pin value to Blynk (non-blocking)."""
    if not BLYNK_TOKEN:
        return

    def _send():
        params = {"token": BLYNK_TOKEN, pin: value}
        try:
            res = requests.get(f"{BLYNK_BASE}/update", params=params, timeout=5)
            if res.status_code != 200:
                print(f"[Blynk] Push failed for {pin}: HTTP {res.status_code} {res.text}")
        except Exception as e:
            print(f"[Blynk] Failed to push {pin}: {e}")
    threading.Thread(target=_send, daemon=True).start()


def _push_many(mapping: dict) -> None:
    """Push multiple virtual pins in one request (non-blocking)."""
    if not BLYNK_TOKEN:
        return

    def _send():
        params = {"token": BLYNK_TOKEN}
        params.update(mapping)
        try:
            res = requests.get(f"{BLYNK_BASE}/update", params=params, timeout=8)
            if res.status_code != 200:
                print(f"[Blynk] Bulk push failed: HTTP {res.status_code} {res.text}")
        except Exception as e:
            print(f"[Blynk] Bulk push failed: {e}")
    threading.Thread(target=_send, daemon=True).start()


def push_sensor_data(data: dict) -> None:
    """Push live sensor readings to Blynk V0-V6 individually."""
    global _last_sensor_push_ts
    now = time.time()
    if now - _last_sensor_push_ts < SENSOR_PUSH_MIN_INTERVAL:
        return
    _last_sensor_push_ts = now

    # Push each sensor value individually for reliability
    _push("V0", data.get("N", 0))
    _push("V1", data.get("P", 0))
    _push("V2", data.get("K", 0))
    _push("V3", data.get("temperature", 0))
    _push("V4", data.get("humidity", 0))
    _push("V5", data.get("ph", 0))
    _push("V6", data.get("rainfall", 0))
    _push("V12", datetime.now().strftime("%d-%m %H:%M:%S"))
    print(f"[Blynk] Sensor data pushed to dashboard (N={data.get('N', 0)}, P={data.get('P', 0)}, K={data.get('K', 0)})")


def push_recommendations(recommendations: list) -> None:
    """Push top 3 crop recommendations to Blynk V7-V11 individually."""
    if not recommendations:
        # Clear recommendation widgets when no results are available.
        _push("V7", "-")
        _push("V8", "-")
        _push("V9", "-")
        _push("V10", "-")
        _push("V11", "-")
        return

    crops = recommendations[:3]

    for i, crop in enumerate(crops):
        name   = str(crop.get("best_crop", "-")).strip() or "-"
        reason = str(crop.get("reason", "-")).strip()[:90] or "-"
        cost_per_hectare = str(crop.get("planting_cost_per_hectare", "-")).strip() or "-"
        harvest_duration = str(crop.get("harvest_duration", "-")).strip() or "-"
        cost   = f"{cost_per_hectare} | {harvest_duration}"

        if i == 0:
            _push("V7", name)
            _push("V8", reason)
            _push("V9", cost)
        elif i == 1:
            _push("V10", name)
        elif i == 2:
            _push("V11", name)

    # Clear any unused slots
    if len(crops) < 2:
        _push("V10", "-")
    if len(crops) < 3:
        _push("V11", "-")

    print(f"[Blynk] Recommendations pushed to dashboard")