"""Farm planner (planner.py): rules always hold and the optimiser finds the true best split."""

import itertools
import math
import unittest
from datetime import date

import _setup
import planner
import recommender

RABI = date(2026, 11, 1)


class Rules(unittest.TestCase):
    def check_plan(self, p, total, plots, irrigated):
        self.assertEqual(len(p["plots"]), plots)
        self.assertAlmostEqual(sum(x["ha"] for x in p["plots"]), total)
        self.assertLessEqual(sum(x["ha"] for x in p["plots"] if x["needs_irrigation"]), irrigated + 1e-9)
        crops = [x["crop"] for x in p["plots"]]
        self.assertEqual(len(crops), len(set(crops)), "a crop appears twice")
        for x in p["plots"]:
            self.assertAlmostEqual(x["ha"] / planner.STEP_HA, round(x["ha"] / planner.STEP_HA))
            self.assertGreaterEqual(x["share"] + 1e-9, p["rules"]["min_share"] - 0.005)
            self.assertLessEqual(x["share"], p["rules"]["max_share"] + 0.005)
        if any(x["share"] > max(planner.MAX_SHARE, 1 / plots) + 0.005 for x in p["plots"]):
            self.assertTrue(p["rules"]["relaxed"], "half-farm limit broken without telling the farmer")
            self.assertTrue(x["schedule"]["steps"], f"{x['crop']} has no fertilizer schedule")
        for k in ("low", "typical", "high"):
            self.assertEqual(p["totals"][k], sum(x["profit"][k] for x in p["plots"]))

    def test_typical_farms(self):
        for total, plots, irrigated in [(12, 3, 6), (12, 2, 6), (5, 3, 5), (2, 1, 0), (20, 3, 10), (3.5, 2, 1)]:
            with self.subTest(total=total, plots=plots, irrigated=irrigated):
                p = planner.plan(_setup.SOIL, total, plots, irrigated, RABI, "Haveli")
                self.check_plan(p, total, plots, irrigated)

    def test_fixed_crop_is_respected(self):
        p = planner.plan(_setup.SOIL, 12, 3, 6, RABI, "Haveli", fixed={"crop": "Wheat", "ha": 4})
        wheat = [x for x in p["plots"] if x["crop"] == "Wheat"]
        self.assertTrue(wheat)
        self.assertGreaterEqual(wheat[0]["ha"], 4)

    def test_loss_warning(self):
        p = planner.plan(_setup.SOIL, 12, 3, 6, RABI, "Haveli")
        for x in p["plots"]:
            self.assertEqual(x["warning"] is not None, x["profit"]["typical"] < 0)

    def test_bad_inputs(self):
        cases = [
            dict(total_ha=0, plots=2, irrigated_ha=0),
            dict(total_ha=12, plots=9, irrigated_ha=6),
            dict(total_ha=1, plots=3, irrigated_ha=1),       # 1 ha = only 2 half-hectare plots
            dict(total_ha=12, plots=3, irrigated_ha=6, fixed={"crop": "Rice", "ha": 2}),   # not in season
            dict(total_ha=12, plots=3, irrigated_ha=6, fixed={"crop": "Grams", "ha": 40}),
        ]
        for c in cases:
            with self.subTest(**{k: str(v) for k, v in c.items()}):
                with self.assertRaises(planner.PlanError):
                    planner.plan(_setup.SOIL, c["total_ha"], c["plots"], c["irrigated_ha"], RABI, "Haveli",
                                 c.get("fixed"))

    def test_no_irrigation_message_names_rainfed_crops(self):
        rec = recommender.recommend(_setup.SOIL, area_ha=1, irrigation=True, on_date=RABI,
                                    taluka="Haveli", top_now=None)
        cands, _ = planner._candidates(rec)
        rainfed = [cd["crop"] for cd in cands if not cd["needs_irrigation"]]
        if len(rainfed) >= len(cands):
            self.skipTest("every candidate is rain-fed for this soil")
        with self.assertRaises(planner.PlanError) as ctx:
            planner.plan(_setup.SOIL, 12, len(cands), 0, RABI, "Haveli")
        self.assertIn("irrigat", str(ctx.exception).lower())
        for crop in rainfed:
            self.assertIn(crop, str(ctx.exception))


class Optimality(unittest.TestCase):
    """Compare the MILP answer with brute force over every allowed split on small farms."""

    def brute_force(self, cands, units, plots, irr_units, min_u, max_u):
        best = -math.inf
        for combo in itertools.combinations(range(len(cands)), plots):
            for split in itertools.product(range(min_u, max_u + 1), repeat=plots):
                if sum(split) != units:
                    continue
                irr = sum(u for i, u in zip(combo, split) if cands[i]["needs_irrigation"])
                if irr > irr_units:
                    continue
                best = max(best, sum(cands[i]["profit"]["typical"] * u * planner.STEP_HA
                                     for i, u in zip(combo, split)))
        return best

    def test_milp_matches_brute_force(self):
        rec = recommender.recommend(_setup.SOIL, area_ha=1, irrigation=True, on_date=RABI,
                                    taluka="Haveli", top_now=None)
        cands, _ = planner._candidates(rec)
        self.assertGreaterEqual(len(cands), 3)
        for units, plots, irr_units in [(8, 2, 4), (10, 3, 5), (6, 2, 0), (12, 3, 12)]:
            with self.subTest(units=units, plots=plots, irrigated=irr_units):
                min_u = max(1, math.ceil(planner.MIN_SHARE * units - 1e-9))
                max_u = max(min_u, math.floor(planner.MAX_SHARE * units))
                expected = self.brute_force(cands, units, plots, irr_units, min_u, max_u)
                chosen = planner._solve(cands, units, plots, irr_units, None, planner.MIN_SHARE, planner.MAX_SHARE)
                if expected == -math.inf:
                    self.assertIsNone(chosen)
                    continue
                got = sum(cd["profit"]["typical"] * u * planner.STEP_HA for cd, u in chosen)
                self.assertAlmostEqual(got, expected, delta=1)


if __name__ == "__main__":
    unittest.main()
