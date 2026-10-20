"""
Simulated field sensor node, used when no real ESP32 is publishing.

Temperature and humidity follow the real current weather for the taluka
(Open-Meteo), with small sensor noise. Soil moisture dries out faster when
it's hot and rises while the pump runs. Time is sped up so a demo shows the
pump cycle within a few minutes.
"""

import random

import weather


class FieldSimulator:
    def __init__(self, taluka: str = "Haveli", start_moisture: float = 42.0):
        self.taluka = taluka
        self.moisture = start_moisture

    def step(self, dt: float, pump_on: bool) -> dict:
        w = weather.get_weather(self.taluka)
        temp = w["temperature_c"] + random.gauss(0, 0.3)
        hum = min(100.0, max(5.0, w["humidity_pct"] + random.gauss(0, 1.0)))

        drying = 0.05 + 0.008 * max(0.0, temp - 15) + 0.002 * max(0.0, 60 - hum)  # % per second
        wetting = 0.9 if pump_on else 0.0
        rain = 0.3 if w["precipitation_now_mm"] > 0 else 0.0
        self.moisture += (wetting + rain - drying) * dt
        self.moisture = min(95.0, max(5.0, self.moisture))

        return {
            "soil_moisture": round(self.moisture + random.gauss(0, 0.2), 1),
            "temperature": round(temp, 1),
            "humidity": round(hum, 1),
            "pump": "ON" if pump_on else "OFF",
        }
