"""
MQTT link between the field node (ESP32 / simulator) and the backend.

  <prefix>/sensor  ESP32 -> backend   {"soil_moisture", "temperature", "humidity", "pump"}
  <prefix>/pump    backend -> ESP32   {"pump": "ON"|"OFF", "mode": "auto"|"manual"}  (retained)

If no real sensor data arrives for SENSOR_STALE_SECONDS, the backend runs its
own FieldSimulator so the dashboard keeps working, and clearly labels the
readings as simulated.
"""

import json
import ssl
import threading
import time

import paho.mqtt.client as mqtt

from config import (
    MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_USERNAME, MQTT_PASSWORD, MQTT_CLIENT_ID,
    TOPIC_SENSOR, TOPIC_PUMP, SENSOR_STALE_SECONDS,
)
from field_sim import FieldSimulator
from irrigation import controller

_lock = threading.Lock()
_latest = None             # latest reading of the device being followed (dict)
_last_real_at = 0.0        # time of the last reading from that device
_devices = {}              # device name -> time it last published

# If several field nodes publish at once, follow only one so the pump isn't
# switched back and forth by two different moisture readings.
SIMULATOR_DEVICES = {"python-simulator"}
_connected = False
_client = None
_sim = FieldSimulator()


# ─── Public API ───────────────────────────────────────────────────────────────

def get_status() -> dict:
    with _lock:
        reading = dict(_latest) if _latest else None
        now = time.time()
        devices = sorted(d for d, t in _devices.items() if now - t < SENSOR_STALE_SECONDS)
    live = now - _last_real_at < SENSOR_STALE_SECONDS
    return {
        "broker": f"{MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}",
        "connected": _connected,
        "source": "mqtt" if live else "simulated",
        "devices_online": devices,
        "reading": reading,
        "irrigation": controller.state(),
    }


def set_taluka(taluka: str):
    _sim.taluka = taluka


def publish_pump(on: bool):
    if _client and _connected:
        payload = json.dumps({"pump": "ON" if on else "OFF", "mode": controller.mode})
        _client.publish(TOPIC_PUMP, payload, qos=1, retain=True)


# ─── MQTT callbacks ───────────────────────────────────────────────────────────

def _on_connect(client, userdata, flags, reason_code, properties):
    global _connected
    _connected = not reason_code.is_failure
    if _connected:
        client.subscribe(TOPIC_SENSOR, qos=0)
        print(f"[MQTT] Connected to {MQTT_BROKER_HOST}, listening on '{TOPIC_SENSOR}'.")
        publish_pump(controller.pump_on)
    else:
        print(f"[MQTT] Connection refused: {reason_code}")


def _on_disconnect(client, userdata, flags, reason_code, properties):
    global _connected
    _connected = False
    print(f"[MQTT] Disconnected ({reason_code}); retrying in the background.")


def _on_message(client, userdata, msg):
    global _latest, _last_real_at
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        reading = {
            "soil_moisture": float(data["soil_moisture"]),
            "temperature": float(data["temperature"]),
            "humidity": float(data["humidity"]),
            "pump": data.get("pump"),
            "device": data.get("device", "esp32"),
            "at": time.time(),
            "source": "mqtt",
        }
    except (ValueError, KeyError, TypeError) as e:
        print(f"[MQTT] Ignored malformed sensor message: {e}")
        return
    with _lock:
        _devices[reading["device"]] = reading["at"]
        if reading["device"] != _active_device(reading["at"]):
            return  # another node is being followed
        _latest = reading
        _last_real_at = reading["at"]
    controller.evaluate(reading)


def _active_device(now: float) -> str | None:
    """The device to follow: a real node beats the Python simulator; newest first."""
    fresh = [d for d, t in _devices.items() if now - t < SENSOR_STALE_SECONDS]
    if not fresh:
        return None
    return min(fresh, key=lambda d: (d in SIMULATOR_DEVICES, -_devices[d]))


# ─── Background threads ───────────────────────────────────────────────────────

def _simulation_loop():
    """Fill in simulated readings whenever the real sensor goes quiet."""
    global _latest
    last = time.time()
    while True:
        time.sleep(1.0)
        now = time.time()
        dt, last = now - last, now
        if now - _last_real_at < SENSOR_STALE_SECONDS:
            continue
        reading = _sim.step(dt, controller.pump_on)
        reading.update({"device": "backend-simulator", "at": now, "source": "simulated"})
        with _lock:
            _latest = reading
        controller.evaluate(reading)


def start():
    global _client
    controller.on_change(publish_pump)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    if MQTT_BROKER_PORT == 8883:
        client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message
    client.reconnect_delay_set(min_delay=2, max_delay=30)
    client.connect_async(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=30)
    client.loop_start()
    _client = client

    threading.Thread(target=_simulation_loop, daemon=True).start()
    print(f"[MQTT] Connecting to {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT} (topics under '{TOPIC_SENSOR.rsplit('/', 1)[0]}')")
