"""
sensor_simulator.py — virtual field node that behaves like the ESP32.

Publishes soil moisture, temperature and humidity to <prefix>/sensor every
2 seconds and listens for pump commands on <prefix>/pump, exactly like the
Wokwi firmware. Temperature/humidity follow the real current weather for the
chosen taluka; soil moisture dries out over time and rises while the pump runs.

Run (backend must be running separately):
    .venv\\Scripts\\python.exe sensor_simulator.py [taluka]
"""

import json
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from config import (  # noqa: E402  (loads backend/.env)
    MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_USERNAME, MQTT_PASSWORD, TOPIC_SENSOR, TOPIC_PUMP,
)
from field_sim import FieldSimulator  # noqa: E402

PUBLISH_INTERVAL = 2.0  # seconds

pump_on = False


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        print(f"[Simulator] Connection refused: {reason_code}")
        return
    client.subscribe(TOPIC_PUMP, qos=1)
    print(f"[Simulator] Connected to {MQTT_BROKER_HOST}. Publishing to '{TOPIC_SENSOR}', "
          f"listening on '{TOPIC_PUMP}'.")


def on_message(client, userdata, msg):
    global pump_on
    try:
        command = json.loads(msg.payload.decode("utf-8")).get("pump")
    except ValueError:
        return
    if command in ("ON", "OFF"):
        pump_on = command == "ON"
        print(f"[Simulator] Pump command received: {command}")


def main():
    taluka = sys.argv[1] if len(sys.argv) > 1 else "Haveli"
    sim = FieldSimulator(taluka=taluka)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"kisanmitra-sim-{int(time.time())}")
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=30)
    client.loop_start()

    last = time.time()
    try:
        while True:
            time.sleep(PUBLISH_INTERVAL)
            now = time.time()
            reading = sim.step(now - last, pump_on)
            last = now
            reading["device"] = "python-simulator"
            client.publish(TOPIC_SENSOR, json.dumps(reading), qos=0)
            print(f"[Simulator] moisture={reading['soil_moisture']}% T={reading['temperature']}°C "
                  f"H={reading['humidity']}% pump={reading['pump']}")
    except KeyboardInterrupt:
        print("\n[Simulator] Stopped.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
