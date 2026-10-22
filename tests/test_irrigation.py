"""Irrigation controller (irrigation.py): thresholds, hysteresis, rain skip and safety cut-off."""

import unittest

import _setup
import irrigation
import weather
from knowledge import WATER_CLASSES


class Controller(unittest.TestCase):
    def setUp(self):
        self.c = irrigation.IrrigationController()
        self.c.set_crop("Wheat")
        self.th = self.c.thresholds()
        self.switches = []
        self.c.on_change(self.switches.append)
        self._weather = weather.get_weather
        self.rain(0)

    def tearDown(self):
        weather.get_weather = self._weather

    def rain(self, mm):
        weather.get_weather = lambda taluka: dict(_setup.FAKE_WEATHER, rain_next_24h_mm=mm)

    def feed(self, moisture):
        self.c.evaluate({"soil_moisture": moisture})
        return self.c.pump_on

    def test_thresholds_come_from_crop_water_need(self):
        from knowledge import CROPS
        self.assertEqual(self.th["moisture_on"], WATER_CLASSES[CROPS["Wheat"]["water_need"]]["moisture_on"])
        self.c.set_crop(None)
        self.assertEqual(self.c.thresholds()["water_class"], "medium")

    def test_hysteresis(self):
        on, off = self.th["moisture_on"], self.th["moisture_off"]
        mid = (on + off) / 2
        self.assertTrue(self.feed(on - 1))
        self.assertTrue(self.feed(mid))          # stays on inside the band
        self.assertFalse(self.feed(off))
        self.assertFalse(self.feed(mid))         # stays off inside the band
        self.assertEqual(self.switches, [True, False])

    def test_waits_for_rain_unless_critically_dry(self):
        on = self.th["moisture_on"]
        self.rain(12)
        self.assertFalse(self.feed(on - 2))
        self.assertIn("rain", self.c.decision["reason"])
        self.assertTrue(self.feed(on - irrigation.CRITICAL_MARGIN - 1))

    def test_manual_mode(self):
        with self.assertRaises(ValueError):
            self.c.set_pump_manual(True)         # still in auto
        self.c.set_mode("manual")
        self.c.set_pump_manual(True)
        self.assertTrue(self.feed(self.th["moisture_off"] + 5))   # auto rules don't apply in manual
        with self.assertRaises(ValueError):
            self.c.set_mode("turbo")

    def test_safety_cut_off_in_manual(self):
        self.c.set_mode("manual")
        self.c.set_pump_manual(True)
        self.assertFalse(self.feed(irrigation.SAFETY_MAX_MOISTURE + 1))
        self.assertIn("Safety", self.c.decision["reason"])

    def test_missing_reading_is_ignored(self):
        self.c.evaluate({"temperature": 30})
        self.assertFalse(self.c.pump_on)


if __name__ == "__main__":
    unittest.main()
