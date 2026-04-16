"""
sensor_simulator.py — Virtual IoT Sensor Publisher
Connects to HiveMQ Cloud and publishes simulated farm sensor data
every 0.8 seconds to the topic: farm/sensor/data
"""

import ssl
import json
import random
import time
import os
import paho.mqtt.client as mqtt

# ─── HiveMQ Cloud Configuration ───────────────────────────────────────────────
BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "")
BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "8883"))
USERNAME = os.getenv("MQTT_USERNAME", "")
PASSWORD = os.getenv("MQTT_PASSWORD", "")
TOPIC = os.getenv("MQTT_TOPIC", "farm/sensor/data")
CLIENT_ID = os.getenv("MQTT_CLIENT_ID_SIM", "crop-sensor-simulator")
PUBLISH_INTERVAL = 0.8  # seconds


# ─── Sensor value ranges (based on Crop_recommendation.csv dataset) ───────────
RANGES = {
    "N":           (0,   140),
    "P":           (5,   145),
    "K":           (5,   205),
    "temperature": (8.0,  44.0),
    "humidity":    (14.0, 100.0),
    "ph":          (3.5,  10.0),
    "rainfall":    (20.0, 300.0),
}


# ─── Shared Base State ────────────────────────────────────────────────────────
BASE_STATE = {}
COMMAND_TOPIC = "farm/sensor/command"

def reset_base_state():
    global BASE_STATE
    BASE_STATE = {
        "N":           random.uniform(*RANGES["N"]),
        "P":           random.uniform(*RANGES["P"]),
        "K":           random.uniform(*RANGES["K"]),
        "temperature": random.uniform(*RANGES["temperature"]),
        "humidity":    random.uniform(*RANGES["humidity"]),
        "ph":          random.uniform(*RANGES["ph"]),
        "rainfall":    random.uniform(*RANGES["rainfall"]),
    }
    print("[Simulator] New soil baseline initialized.")

def generate_sensor_data() -> dict:
    if not BASE_STATE:
        reset_base_state()

    def deflect(val, min_val, max_val):
        change_pct = random.uniform(-0.02, 0.02)
        new_val = val + (val * change_pct)
        return max(min_val, min(new_val, max_val))

    for key in BASE_STATE:
        BASE_STATE[key] = deflect(BASE_STATE[key], *RANGES[key])

    return {
        "N":           round(BASE_STATE["N"], 1),
        "P":           round(BASE_STATE["P"], 1),
        "K":           round(BASE_STATE["K"], 1),
        "temperature": round(BASE_STATE["temperature"], 2),
        "humidity":    round(BASE_STATE["humidity"], 2),
        "ph":          round(BASE_STATE["ph"], 2),
        "rainfall":    round(BASE_STATE["rainfall"], 2),
        "source":      "python-simulator",
    }

# ─── MQTT Callbacks ───────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[Simulator] [SUCCESS] Connected to HiveMQ Cloud")
        print(f"[Simulator] Publishing to topic '{TOPIC}' every {PUBLISH_INTERVAL}s")
        client.subscribe(COMMAND_TOPIC, qos=1)
        print(f"[Simulator] Subscribed to command topic '{COMMAND_TOPIC}'")
        print("-" * 55)
    else:
        print(f"[Simulator] [ERROR] Connection failed (rc={rc})")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        if payload.get("command") == "refresh":
            reset_base_state()
    except Exception:
        pass

def on_publish(client, userdata, mid):
    pass  # Quiet publish confirmation


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION1,
        client_id=f"{CLIENT_ID}-{random.randint(1000, 9999)}",
        clean_session=True,
    )
    if USERNAME and PASSWORD:
        client.username_pw_set(USERNAME, PASSWORD)
    if BROKER_PORT == 8883:
        client.tls_set(tls_version=ssl.PROTOCOL_TLS)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_publish = on_publish

    print(f"[Simulator] Connecting to {BROKER_HOST}:{BROKER_PORT} ...")
    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    except Exception as e:
        print(f"[Simulator] Failed to connect: {e}")
        return

    client.loop_start()
    time.sleep(2)  # Wait for connection

    try:
        count = 0
        while True:
            count += 1
            data = generate_sensor_data()
            payload = json.dumps(data)
            result = client.publish(TOPIC, payload, qos=1)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                print(f"[Simulator] Publish failed (rc={result.rc})")
            print(
                f"[#{count:04d}]  N={data['N']:6.1f}  P={data['P']:6.1f}  "
                f"K={data['K']:6.1f}  Temp={data['temperature']:5.1f}°C  "
                f"Hum={data['humidity']:5.1f}%  pH={data['ph']:4.2f}  "
                f"Rain={data['rainfall']:6.1f}mm"
            )
            time.sleep(PUBLISH_INTERVAL)
    except KeyboardInterrupt:
        print("\n[Simulator] Stopped by user.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
