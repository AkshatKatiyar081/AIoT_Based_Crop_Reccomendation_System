"""Mandi prices, yields and profit (market.py)."""

import unittest
from datetime import date
from unittest import mock

import _setup
import market
from knowledge import CROPS


class Prices(unittest.TestCase):
    def test_price_filter(self):
        self.assertIsNone(market._valid("40"))         # per-bunch leafy-vegetable quote
        self.assertIsNone(market._valid("n/a"))
        self.assertEqual(market._valid("2150"), 2150.0)

    def test_every_crop_has_a_price_source(self):
        for crop, info in CROPS.items():
            m = info["market"]
            self.assertTrue(m.get("commodity") or m.get("fixed_price_per_quintal"), crop)

    def test_sugarcane_uses_frp(self):
        p = market.live_price("Sugarcane")
        self.assertEqual(p["level"], "fixed")
        self.assertEqual(p["price"], 355)

    def test_live_price_prefers_pune_then_state(self):
        records = [
            {"commodity": "Onion", "district": "Pune", "market": "Pune", "modal_price": "2000", "arrival_date": "21/10/2026"},
            {"commodity": "Onion", "district": "Pune", "market": "Manchar", "modal_price": "2400", "arrival_date": "21/10/2026"},
            {"commodity": "Onion", "district": "Nashik", "market": "Lasalgaon", "modal_price": "1500", "arrival_date": "21/10/2026"},
            {"commodity": "Wheat", "district": "Ahmednagar", "market": "Rahuri", "modal_price": "2700", "arrival_date": "21/10/2026"},
            {"commodity": "Wheat", "district": "Satara", "market": "Karad", "modal_price": "2900", "arrival_date": "21/10/2026"},
        ]
        with mock.patch.object(market, "_live_records", return_value=records):
            onion = market.live_price("Onion")
            wheat = market.live_price("Wheat")
        self.assertEqual((onion["level"], onion["price"]), ("Pune district", 2200))
        self.assertEqual((wheat["level"], wheat["price"]), ("Maharashtra", 2800))

    def test_no_live_data_is_none_not_a_guess(self):
        with mock.patch.object(market, "_live_records", return_value=[]):
            self.assertIsNone(market.live_price("Onion"))

    def test_harvest_price_range(self):
        for crop in ("Onion", "Wheat", "Grams", "Maize"):
            for month in (1, 3, 6, 10):
                p = market.harvest_price(crop, month)
                if p:
                    self.assertLessEqual(p["low"], p["high"], f"{crop} month {month}")
                    self.assertGreaterEqual(p["median"], market.MIN_VALID_PRICE)


class Profit(unittest.TestCase):
    def test_profit_arithmetic(self):
        e = market.economics("Onion", date(2026, 11, 1), 2, 5000)
        self.assertFalse(e["missing"])
        q = e["yield"]["t_per_ha"] * 10
        lo, hi = e["cost_per_ha"]
        self.assertAlmostEqual(e["profit_per_ha"]["typical"], q * e["expected_price"]["median"] - (lo + hi) / 2, delta=1)
        self.assertAlmostEqual(e["profit_per_ha"]["low"], q * e["expected_price"]["low"] - hi, delta=1)
        self.assertAlmostEqual(e["profit_per_ha"]["high"], q * e["expected_price"]["high"] - lo, delta=1)
        self.assertAlmostEqual(e["profit_total"]["typical"], 2 * e["profit_per_ha"]["typical"], delta=2)
        self.assertLessEqual(e["profit_per_ha"]["low"], e["profit_per_ha"]["typical"])
        self.assertLessEqual(e["profit_per_ha"]["typical"], e["profit_per_ha"]["high"])

    def test_harvest_month_from_duration(self):
        e = market.economics("Wheat", date(2026, 11, 1), 1, 0)
        self.assertIn("2027", e["harvest_month"])

    def test_missing_yield_is_reported(self):
        for crop in ("Spinach", "Methi"):
            if crop in CROPS:
                e = market.economics(crop, date(2026, 11, 1), 1, 0)
                self.assertIsNone(e["profit_per_ha"])
                self.assertIn("district yield data", e["missing"])

    def test_paddy_conversion(self):
        y = market.crop_yield("Rice", "Paddy(Dhan)(Common)")
        self.assertAlmostEqual(y["t_per_ha"], round(1.52 / market.PADDY_TO_RICE, 2), delta=0.01)


if __name__ == "__main__":
    unittest.main()
