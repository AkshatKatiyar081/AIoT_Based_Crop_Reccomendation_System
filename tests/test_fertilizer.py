"""Stage-wise fertilizer schedule and costs (fertilizer.py, crops.json)."""

import unittest
from datetime import date

import _setup
import fertilizer
from knowledge import CROPS


class ScheduleData(unittest.TestCase):
    def test_every_crop_has_a_schedule_that_adds_up(self):
        for crop, info in CROPS.items():
            sched = info["schedule"]
            self.assertIn(sched["status"], {"verified", "partial", "general"}, crop)
            if sched["status"] != "general":     # "general" schedules are labelled as general practice
                self.assertTrue(sched["sources"], f"{crop} schedule has no source")
            for nutrient in ("N", "P", "K"):
                total = sum(s[nutrient] for s in sched["splits"])
                self.assertAlmostEqual(total, 1.0, places=6, msg=f"{crop} {nutrient} splits sum to {total}")
            days = [s["day"] for s in sched["splits"]]
            self.assertEqual(days, sorted(days), f"{crop} splits are out of order")


class Schedule(unittest.TestCase):
    def _products_total(self, steps, product):
        return sum(p["kg_per_ha"] for s in steps for p in s["products"] if p["product"] == product)

    def test_nitrogen_delivered_equals_need_with_dap(self):
        # DAP brings N with the basal dose; later urea splits must be reduced, not the total exceeded
        for crop in CROPS:
            need = {"N": 120.0, "P2O5": 60.0, "K2O": 40.0}
            sched = fertilizer.application_schedule(crop, need, "dap", 1, date(2026, 11, 1))
            n = (self._products_total(sched["steps"], "DAP") * fertilizer.DAP_N
                 + self._products_total(sched["steps"], "Urea") * fertilizer.UREA_N)
            self.assertAlmostEqual(n, max(need["N"], need["P2O5"] / fertilizer.DAP_P2O5 * fertilizer.DAP_N),
                                   delta=1.0, msg=crop)

    def test_sugarcane_n_carry_over(self):
        need = {"N": 250.0, "P2O5": 115.0, "K2O": 115.0}
        sched = fertilizer.application_schedule("Sugarcane", need, "dap", 1, date(2026, 11, 1))
        n = (self._products_total(sched["steps"], "DAP") * fertilizer.DAP_N
             + self._products_total(sched["steps"], "Urea") * fertilizer.UREA_N)
        self.assertAlmostEqual(n, 250, delta=1.0)

    def test_dates_and_status(self):
        start = date(2026, 11, 1)
        sched = fertilizer.application_schedule("Wheat", {"N": 120, "P2O5": 60, "K2O": 40}, "dap", 2,
                                                start, today=date(2026, 11, 22))
        by_day = {s["day"]: s for s in sched["steps"]}
        self.assertEqual(by_day[0]["date"], "2026-11-01")
        self.assertEqual(by_day[0]["status"], "done")
        statuses = [s["status"] for s in sched["steps"]]
        self.assertIn("due", statuses)        # wheat's crown-root-initiation dose falls ~day 21
        self.assertTrue(all(s["date"] >= "2026-11-01" for s in sched["steps"]))

    def test_rain_warning_only_for_due_urea(self):
        start = date(2026, 11, 1)
        wet = {"forecast": [{"rain_mm": 8}, {"rain_mm": 6}]}
        sched = fertilizer.application_schedule("Wheat", {"N": 120, "P2O5": 60, "K2O": 40}, "dap", 1,
                                                start, weather=wet, today=date(2026, 11, 22))
        self.assertEqual(sched["rain_next_2_days_mm"], 14)
        for s in sched["steps"]:
            warned = any("rain is forecast" in t for t in s["tips"])
            has_urea = any(p["product"] == "Urea" for p in s["products"])
            self.assertEqual(warned, s["status"] == "due" and has_urea, s["stage"])

    def test_no_warning_below_threshold(self):
        dry = {"forecast": [{"rain_mm": 4}, {"rain_mm": 5}]}
        sched = fertilizer.application_schedule("Wheat", {"N": 120, "P2O5": 60, "K2O": 40}, "dap", 1,
                                                date(2026, 11, 1), weather=dry, today=date(2026, 11, 22))
        self.assertFalse(any("rain is forecast" in t for s in sched["steps"] for t in s["tips"]))


class Costs(unittest.TestCase):
    def test_bag_prices(self):
        self.assertEqual(fertilizer.product_cost("Urea", 45), 242)
        self.assertEqual(fertilizer.product_cost("DAP", 50), 1350)
        self.assertAlmostEqual(fertilizer.product_cost("Urea", 90), 484)

    def test_advise_costs_scale_with_area(self):
        one = fertilizer.advise("Onion", _setup.SOIL, 1, start=date(2026, 11, 1))
        three = fertilizer.advise("Onion", _setup.SOIL, 3, start=date(2026, 11, 1))
        for a, b in zip(one["dose_options"], three["dose_options"]):
            self.assertEqual(a["cost_per_ha"], b["cost_per_ha"])
            self.assertAlmostEqual(b["cost_total"], 3 * a["cost_total"], delta=3 * len(a["products"]))
        self.assertEqual(one["schedule"]["option"], one["dose_options"][0]["id"])

    def test_low_phosphorus_raises_dose(self):
        low_p = dict(_setup.SOIL, P=8)
        high_p = dict(_setup.SOIL, P=60)
        need_low = fertilizer.advise("Wheat", low_p, 1)["nutrient_need_kg_per_ha"]["P2O5"]
        need_high = fertilizer.advise("Wheat", high_p, 1)["nutrient_need_kg_per_ha"]["P2O5"]
        self.assertGreater(need_low, need_high)


if __name__ == "__main__":
    unittest.main()
