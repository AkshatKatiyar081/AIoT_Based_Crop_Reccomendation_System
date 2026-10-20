"""
Irrigation controller.

Auto mode switches the pump using soil moisture + the rain forecast:
  - moisture below the crop's ON threshold  -> pump ON
    (unless meaningful rain is forecast and the soil isn't critically dry)
  - moisture above the crop's OFF threshold -> pump OFF
  - in between                              -> keep the current state (hysteresis,
    so the pump doesn't flicker on and off around one value)
Manual mode lets the farmer switch the pump from the dashboard.
"""

import threading
import time

from knowledge import CROPS, WATER_CLASSES
import weather

RAIN_SKIP_MM = 5.0        # forecast rain that's worth waiting for
CRITICAL_MARGIN = 10.0    # % below the ON threshold where we irrigate even if rain is coming
SAFETY_MAX_MOISTURE = 90.0  # pump is always switched off above this, even in manual mode


class IrrigationController:
    def __init__(self):
        self._lock = threading.Lock()
        self.mode = "auto"
        self.pump_on = False
        self.crop = None
        self.taluka = "Haveli"
        self.decision = {"action": "idle", "reason": "Waiting for sensor data.", "at": None}
        self._on_change = None  # callback(pump_on: bool)

    # ── configuration ──
    def on_change(self, callback):
        self._on_change = callback

    def thresholds(self) -> dict:
        water_class = CROPS[self.crop]["water_need"] if self.crop in CROPS else "medium"
        return {"water_class": water_class, **WATER_CLASSES[water_class]}

    def set_mode(self, mode: str):
        if mode not in ("auto", "manual"):
            raise ValueError("mode must be 'auto' or 'manual'")
        with self._lock:
            self.mode = mode
            self.decision = {"action": "mode", "reason": f"Switched to {mode} mode.", "at": time.time()}

    def set_crop(self, crop: str | None, taluka: str | None = None):
        with self._lock:
            self.crop = crop if crop in CROPS else None
            if taluka:
                self.taluka = taluka

    def set_pump_manual(self, on: bool):
        with self._lock:
            if self.mode != "manual":
                raise ValueError("Switch to manual mode to control the pump yourself.")
            self.decision = {"action": "manual", "reason": f"Pump turned {'ON' if on else 'OFF'} by farmer.",
                             "at": time.time()}
        self._apply(on)

    # ── automatic decision ──
    def evaluate(self, sensor: dict):
        if sensor.get("soil_moisture") is None:
            return
        moisture = float(sensor["soil_moisture"])

        # Safety cut-off applies in every mode, so a forgotten manual pump can't flood the field
        if self.pump_on and moisture >= SAFETY_MAX_MOISTURE:
            with self._lock:
                self.decision = {"action": "off", "at": time.time(),
                                 "reason": f"Safety cut-off: soil moisture {moisture:.0f}% is above "
                                           f"{SAFETY_MAX_MOISTURE:.0f}%, so the pump was switched off."}
            self._apply(False)
            return
        if self.mode != "auto":
            return
        th = self.thresholds()
        rain = weather.get_weather(self.taluka)["rain_next_24h_mm"]
        crop_txt = self.crop or "default (medium water need)"

        if moisture < th["moisture_on"]:
            if rain >= RAIN_SKIP_MM and moisture >= th["moisture_on"] - CRITICAL_MARGIN:
                target, reason = False, (f"Soil moisture {moisture:.0f}% is below {th['moisture_on']}% for {crop_txt}, "
                                         f"but {rain:.1f} mm rain is forecast in 24 h, so waiting for rain.")
            else:
                target, reason = True, (f"Soil moisture {moisture:.0f}% is below {th['moisture_on']}% "
                                        f"for {crop_txt}; irrigating.")
        elif moisture >= th["moisture_off"]:
            target, reason = False, (f"Soil moisture {moisture:.0f}% reached {th['moisture_off']}%; "
                                     f"enough water for {crop_txt}.")
        else:
            target = self.pump_on
            reason = (f"Soil moisture {moisture:.0f}% is within the target band "
                      f"({th['moisture_on']}–{th['moisture_off']}%); keeping pump {'ON' if target else 'OFF'}.")

        with self._lock:
            self.decision = {"action": "on" if target else "off", "reason": reason, "at": time.time()}
        self._apply(target)

    def _apply(self, on: bool):
        changed = on != self.pump_on
        self.pump_on = on
        if changed and self._on_change:
            self._on_change(on)

    def state(self) -> dict:
        return {
            "mode": self.mode, "pump_on": self.pump_on, "crop": self.crop, "taluka": self.taluka,
            "thresholds": self.thresholds(), "decision": self.decision,
        }


controller = IrrigationController()
