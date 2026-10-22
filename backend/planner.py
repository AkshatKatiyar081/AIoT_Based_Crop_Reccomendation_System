"""
Farm planner: split a farm into plots and choose a crop for each, to maximise
expected profit under practical rules. Solved as a small mixed-integer
linear program (scipy.optimize.milp).

Decision variables, for every candidate crop i:
    x_i  land given to the crop, in steps of STEP_HA (integer)
    y_i  1 if the crop is grown at all (binary)

Maximise   sum_i  typical_profit_per_ha_i * x_i * STEP_HA
subject to sum_i x_i = total land                      (all land is used)
           sum_i y_i = number of plots                  (one crop per plot)
           min_share * total * y_i <= x_i <= max_share * total * y_i
           sum of land under crops that need irrigation <= irrigated land
           x_fixed >= fixed area, y_fixed = 1           (optional farmer choice)

Candidates are the crops the soil model rates suitable (>= 0.30) whose sowing
window is open on the chosen date and whose profit can be estimated (yield and
harvest-month price known). Profit uses the same numbers shown on each crop
card: district yield x typical harvest-month price - cost of cultivation.
"""

import math
from datetime import date

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

import fertilizer
import recommender

STEP_HA = 0.5          # plot sizes move in half-hectare steps
MIN_SHARE = 0.10       # each plot is at least 10% of the farm
MAX_SHARE = 0.50       # no crop takes more than half the farm (spreads price risk)


class PlanError(ValueError):
    pass


def _candidates(rec: dict) -> tuple[list[dict], list[dict]]:
    usable, excluded = [], []
    for c in rec["sow_now"]:
        e = c["economics"]
        if not e["profit_per_ha"]:
            excluded.append({"crop": c["crop"], "reason": "no " + " or ".join(e["missing"])})
            continue
        usable.append({
            "crop": c["crop"], "marathi": c["marathi"], "suitability": c["suitability"],
            "profit": e["profit_per_ha"], "needs_irrigation": not c["water"]["feasible_without_irrigation"],
            "water_need": c["water_need"], "economics": e, "season": c["season"],
        })
    for c in rec["later"]:
        excluded.append({"crop": c["crop"], "reason": c["season"]["label"].lower()})
    return usable, excluded


def _solve(cands, units, plots, irrigated_units, fixed, min_share, max_share):
    n = len(cands)
    # variables: x_0..x_{n-1}, y_0..y_{n-1}
    c = np.zeros(2 * n)
    c[:n] = [-cd["profit"]["typical"] * STEP_HA for cd in cands]   # milp minimises
    integrality = np.ones(2 * n)
    lb = np.zeros(2 * n)
    ub = np.concatenate([np.full(n, units), np.ones(n)])

    rows, lo, hi = [], [], []

    def add(row, low, high):
        rows.append(row); lo.append(low); hi.append(high)

    row = np.zeros(2 * n); row[:n] = 1; add(row, units, units)                 # all land used
    row = np.zeros(2 * n); row[n:] = 1; add(row, plots, plots)                 # number of plots
    min_u = max(1, math.ceil(min_share * units - 1e-9))
    max_u = units if plots == 1 else max(min_u, math.floor(max_share * units))
    for i in range(n):
        row = np.zeros(2 * n); row[i] = 1; row[n + i] = -min_u; add(row, 0, np.inf)   # x_i >= min * y_i
        row = np.zeros(2 * n); row[i] = 1; row[n + i] = -max_u; add(row, -np.inf, 0)  # x_i <= max * y_i
    row = np.zeros(2 * n)
    for i, cd in enumerate(cands):
        if cd["needs_irrigation"]:
            row[i] = 1
    add(row, -np.inf, irrigated_units)                                         # irrigation limit
    if fixed:
        i = next(k for k, cd in enumerate(cands) if cd["crop"] == fixed["crop"])
        lb[i] = max(lb[i], fixed["units"])
        lb[n + i] = 1

    res = milp(c, integrality=integrality, bounds=Bounds(lb, ub),
               constraints=LinearConstraint(np.array(rows), lo, hi), options={"time_limit": 10})
    if not res.success:
        return None
    x = np.round(res.x[:n]).astype(int)
    return [(cands[i], int(x[i])) for i in range(n) if x[i] > 0]


def _best_single_crop(cands, total_ha, irrigated_ha):
    """Baseline: the most profitable single crop on the whole farm that the water allows."""
    allowed = [cd for cd in cands if not cd["needs_irrigation"] or irrigated_ha >= total_ha]
    if not allowed:
        return None
    best = max(allowed, key=lambda cd: cd["profit"]["typical"])
    return {"crop": best["crop"], **{k: round(v * total_ha) for k, v in best["profit"].items()}}


def plan(soil: dict, total_ha: float, plots: int, irrigated_ha: float, sow_date: date,
         taluka: str, fixed: dict | None = None) -> dict:
    if total_ha <= 0 or total_ha > 500:
        raise PlanError("Total land must be between 0.5 and 500 hectares.")
    units = int(round(total_ha / STEP_HA))
    if units < 1:
        raise PlanError("Total land must be at least 0.5 hectare.")
    total_ha = units * STEP_HA
    irrigated_ha = max(0.0, min(irrigated_ha, total_ha))
    if plots < 1 or plots > 6:
        raise PlanError("Number of plots must be between 1 and 6.")
    if plots > units:
        raise PlanError(f"{total_ha:g} ha can be split into at most {units} plots of {STEP_HA:g} ha.")

    rec = recommender.recommend(soil, area_ha=1, irrigation=irrigated_ha > 0, on_date=sow_date,
                                taluka=taluka, top_now=None)
    cands, excluded = _candidates(rec)
    if len(cands) < plots:
        names = ", ".join(cd["crop"] for cd in cands) or "none"
        raise PlanError(f"Only {len(cands)} crop(s) can be planned for this soil and sowing date ({names}). "
                        f"Choose {max(1, len(cands))} plot(s) or another sowing date.")

    fixed_spec = None
    if fixed and fixed.get("crop"):
        if fixed["crop"] not in [cd["crop"] for cd in cands]:
            raise PlanError(f"{fixed['crop']} can't be planned now: it isn't suitable, in season, or priced for this soil.")
        f_units = int(round(float(fixed.get("ha") or 0) / STEP_HA))
        if f_units < 1 or f_units > units:
            raise PlanError("The fixed crop's area must be between 0.5 ha and the total land.")
        fixed_spec = {"crop": fixed["crop"], "units": f_units}

    irrigated_units = int(math.floor(irrigated_ha / STEP_HA + 1e-9))
    rainfed = [cd["crop"] for cd in cands if not cd["needs_irrigation"]]
    if irrigated_units == 0 and len(rainfed) < plots:
        raise PlanError(
            f"Without irrigation, only {len(rainfed)} crop(s) can be grown from this sowing date"
            f"{' (' + ', '.join(rainfed) + ')' if rainfed else ''}. "
            f"Choose {max(1, len(rainfed))} plot(s), or enter how much of your land is irrigated.")
    # Relax the share rules only when the farmer's own choices make them impossible
    min_share = min(MIN_SHARE, 1 / plots)
    max_share = max(MAX_SHARE, 1 / plots, (fixed_spec["units"] / units) if fixed_spec else 0)
    chosen = _solve(cands, units, plots, irrigated_units, fixed_spec, min_share, max_share)
    if chosen is None:
        chosen = _solve(cands, units, plots, irrigated_units, fixed_spec, min_share, 1.0)
    if chosen is None:
        raise PlanError("No plan fits these limits. Try more irrigated land, fewer plots, or no fixed crop.")

    result_plots = []
    for cd, u in sorted(chosen, key=lambda t: -t[1]):
        ha = u * STEP_HA
        fert = fertilizer.advise(cd["crop"], rec["soil"], ha,
                                 start=sow_date, irrigation=cd["needs_irrigation"])
        result_plots.append({
            "crop": cd["crop"], "marathi": cd["marathi"], "ha": ha, "share": round(ha / total_ha, 3),
            "suitability": cd["suitability"], "needs_irrigation": cd["needs_irrigation"],
            "water_need": cd["water_need"],
            "profit": {k: round(v * ha) for k, v in cd["profit"].items()},
            "profit_per_ha": cd["profit"], "economics": cd["economics"],
            "fertilizer_cost": fert["dose_options"][0]["cost_total"],
            "schedule": fert["schedule"],
            "warning": (f"{cd['crop']} is expected to make a loss in a typical year; it is here only because "
                        f"you asked for {plots} plots. Consider one plot fewer."
                        if cd["profit"]["typical"] < 0 else None),
        })

    totals = {k: sum(p["profit"][k] for p in result_plots) for k in ("low", "typical", "high")}
    baseline = _best_single_crop(cands, total_ha, irrigated_ha)
    return {
        "total_ha": total_ha, "plots": result_plots, "totals": totals,
        "irrigated_ha": irrigated_ha, "sowing_date": sow_date.isoformat(),
        "baseline_single_crop": baseline,
        "gain_vs_single_crop": None if not baseline else totals["typical"] - baseline["typical"],
        "candidates": [{"crop": cd["crop"], "typical_per_ha": cd["profit"]["typical"],
                        "needs_irrigation": cd["needs_irrigation"]} for cd in cands],
        "excluded": excluded,
        "confidence": rec["confidence"],
        "rules": {"step_ha": STEP_HA, "min_share": round(min_share, 2), "max_share": round(max_share, 2)},
    }
