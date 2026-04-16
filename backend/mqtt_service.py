import ssl
import json
import random
import threading
import time
import collections
import paho.mqtt.client as mqtt
import blynk_service

from config import (
    MQTT_BROKER_HOST, MQTT_BROKER_PORT,
    MQTT_USERNAME, MQTT_PASSWORD,
    MQTT_TOPIC, MQTT_CLIENT_ID, SENSOR_RANGES
)

# ─── Shared state ─────────────────────────────────────────────────────────────
_lock          = threading.Lock()
_latest_data   = None          # Most recent sensor payload
_history       = collections.deque(maxlen=50)
_mqtt_connected = False
_use_simulation = False        # Flipped to True if MQTT fails
_client        = None

def publish_command(command: str):
    if _client and _mqtt_connected:
        try:
            _client.publish("farm/sensor/command", json.dumps({"command": command}), qos=1)
        except Exception as e:
            print(f"[MQTT] Failed to publish command: {e}")

def get_latest_sensor_data() -> dict:
    """Return the most recent sensor data (MQTT or simulated)."""
    # If MQTT is connected and we have cached data, return it
    if _mqtt_connected:
        with _lock:
            if _latest_data is not None:
                return dict(_latest_data)
    # MQTT not connected or no data received yet — always generate fresh simulated data
    return _simulate_sensor()


def _simulate_sensor() -> dict:
    """Generate realistic random sensor values within crop-dataset ranges."""
    r = SENSOR_RANGES
    return {
        "N":           round(random.uniform(*r["N"]),           2),
        "P":           round(random.uniform(*r["P"]),           2),
        "K":           round(random.uniform(*r["K"]),           2),
        "temperature": round(random.uniform(*r["temperature"]), 2),
        "humidity":    round(random.uniform(*r["humidity"]),    2),
        "ph":          round(random.uniform(*r["ph"]),          2),
        "rainfall":    round(random.uniform(*r["rainfall"]),    2),
        "source":      "simulated",
    }


# ─── MQTT Callbacks ───────────────────────────────────────────────────────────

def _on_connect(client, userdata, flags, rc):
    global _mqtt_connected
    if rc == 0:
        _mqtt_connected = True
        print(f"[MQTT] Connected to HiveMQ Cloud broker.")
        client.subscribe(MQTT_TOPIC, qos=1)
        print(f"[MQTT] Subscribed to topic: {MQTT_TOPIC}")
    else:
        _mqtt_connected = False
        print(f"[MQTT] Connection failed (rc={rc}). Using simulated sensor data.")


def _on_disconnect(client, userdata, rc):
    global _mqtt_connected
    _mqtt_connected = False
    if rc != 0:
        print(f"[MQTT] Unexpected disconnect (rc={rc}). Will attempt reconnect.")


def _on_message(client, userdata, msg):
    global _latest_data
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        payload["source"] = "mqtt"
        with _lock:
            _latest_data = payload
            _history.append(payload)
            blynk_service.push_sensor_data(payload)  # Push live data to Blynk dashboard
    except Exception as e:
        print(f"[MQTT] Failed to parse message: {e}")

def get_averaged_sensor_data(duration_seconds: float = 3.5) -> dict:
    if not _mqtt_connected or _use_simulation:
        time.sleep(duration_seconds)
        return _simulate_sensor()

    with _lock:
        _history.clear()

    print(f"[MQTT] Collecting average sensor data for {duration_seconds} seconds...")
    time.sleep(duration_seconds)

    with _lock:
        collected = list(_history)

    if not collected:
        return get_latest_sensor_data()

    avg_data = {"N": 0.0, "P": 0.0, "K": 0.0, "temperature": 0.0, "humidity": 0.0, "ph": 0.0, "rainfall": 0.0}
    for c in collected:
        for k in avg_data:
            avg_data[k] += float(c.get(k, 0))

    count = len(collected)
    for k in avg_data:
        avg_data[k] = round(avg_data[k] / count, 2)

    avg_data["source"] = f"mqtt_avg_samples:{count}"
    return avg_data


# ─── Background MQTT thread ───────────────────────────────────────────────────

def _run_mqtt_client():
    global _use_simulation, _client
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=MQTT_CLIENT_ID, clean_session=True)
        _client = client
        if MQTT_USERNAME and MQTT_PASSWORD:
            client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        if MQTT_BROKER_PORT == 8883:
            client.tls_set(tls_version=ssl.PROTOCOL_TLS)

        client.on_connect    = _on_connect
        client.on_disconnect = _on_disconnect
        client.on_message    = _on_message

        client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=60)
        client.loop_forever()
    except Exception as e:
        _use_simulation = True
        print(f"[MQTT] Could not start MQTT client: {e}. Falling back to simulation.")


def _push_simulated_data_loop():
    """Continuously generate and push simulated sensor data to Blynk when MQTT is not connected."""
    while True:
        time.sleep(1.0)  # Push every 1 second
        if not _mqtt_connected:
            data = _simulate_sensor()
            blynk_service.push_sensor_data(data)


def start_mqtt_subscriber():
    """Launch the MQTT client in a daemon thread."""
    thread = threading.Thread(target=_run_mqtt_client, daemon=True)
    thread.start()
    print("[MQTT] Subscriber thread started.")
    
    # Also start a background thread to push simulated data to Blynk when MQTT is unavailable
    blynk_thread = threading.Thread(target=_push_simulated_data_loop, daemon=True)
    blynk_thread.start()
    print("[Blynk] Simulation pusher thread started.")
