"""
Crop recommendation = ML soil suitability + season rules + water check + knowledge base.

1. The Random Forest (trained on real Pune Soil Health Cards) scores how well
   each of the 17 crops suits the soil.
2. A confidence check compares the soil card with the training data, so the
   app can say when a soil looks unlike anything it learned from.
3. Season rules split crops into "sow now" and "later this year".
4. A water check flags crops whose need exceeds the expected seasonal rain
   when the farmer has no irrigation.
"""

from datetime import date

import numpy as np
from joblib import load

from config import CROP_MODEL_PATH
import district
import fertilizer
from knowledge import CROPS, month_names
from soil_ratings import rate, encode_soil, ph_class, LEVEL_NAMES, PLAUSIBLE, UNITS

SUITABLE_THRESHOLD = 0.30   # minimum model score to call a crop suitable
TOP_NOW = 5
TOP_LATER = 3

# Share of annual rainfall that falls in each season in Pune district (approximate)
SEASON_RAIN_SHARE = {"kharif": 0.85, "rabi": 0.10, "summer": 0.05}
# Rabi crops also use moisture stored in the soil after the monsoon (approximate, mm)
SEASON_RESIDUAL_MM = {"kharif": 0, "rabi": 150, "summer": 0}
SEASON_OF_MONTH = {**{m: "kharif" for m in (6, 7, 8, 9)},
                   **{m: "rabi" for m in (10, 11, 12)},
                   **{m: "summer" for m in (1, 2, 3, 4, 5)}}

try:
    _bundle = load(CROP_MODEL_PATH)
    print("[ML] Pune crop model loaded.")
except Exception as e:  # model not trained yet
    _bundle = None
    print(f"[ML] Could not load crop model ({e}). Run ml/train_crop_model.py first.")


class SoilCardError(ValueError):
    pass


# ─── Input handling ───────────────────────────────────────────────────────────

SOIL_FIELDS = ["pH", "OC", "N", "P", "K", "S", "Zn", "B", "Fe", "Mn", "Cu"]


def parse_soil_card(raw: dict) -> dict:
    """Validate a soil card from the dashboard; raise SoilCardError on bad input."""
    soil, missing, errors = {}, [], []
    for field in SOIL_FIELDS:
        value = raw.get(field)
        try:
            value = float(value)
        except (TypeError, ValueError):
            missing.append(field)
            continue
        lo, hi = PLAUSIBLE[field]
        if not lo <= value <= hi:
            unit = f" {UNITS[field]}" if UNITS[field] else ""
            errors.append(f"{field} = {value:g}{unit} is not a realistic soil value (expected {lo}–{hi}).")
        soil[field] = value
    if missing:
        errors.insert(0, f"Please fill in every soil card value. Missing: {', '.join(missing)}.")
    if errors:
        raise SoilCardError(" ".join(errors))
    return soil


def _encode(soil: dict) -> np.ndarray:
    return np.array([encode_soil(soil)], dtype=float)


# ─── Confidence (out-of-distribution check) ──────────────────────────────────

def _confidence(x: np.ndarray, soil: dict) -> dict:
    ref = _bundle["reference"]
    warnings = []

    for i, f in enumerate(_bundle["features"]):
        if f not in ref["numeric_ranges"]:
            continue
        lo, hi = ref["numeric_ranges"][f]
        margin = 0.1 * (hi - lo)
        if not lo - margin <= soil[f] <= hi + margin:
            unit = f" {UNITS[f]}" if UNITS[f] else ""
            warnings.append(f"{f} = {soil[f]:g}{unit} is outside the range seen in Pune soil data "
                            f"({lo:g}–{hi:g}{unit}). Please double-check your soil card.")

    z = (x[0] - ref["mean"]) / ref["std"]
    nearest = float(np.sqrt(((ref["Z"] - z) ** 2).sum(axis=1)).min())

    if nearest <= ref["nn_p75"] and not warnings:
        level = "High"
    elif nearest <= ref["nn_p95"]:
        level = "Medium"
    else:
        level = "Low"
        warnings.append("This soil profile is unlike any soil card in our Pune data, "
                        "so the recommendation has low confidence.")
    if warnings and level == "High":
        level = "Medium"

    return {"level": level, "nearest_distance": round(nearest, 2), "warnings": warnings}


# ─── Season and water rules ───────────────────────────────────────────────────

def _season_status(crop: str, month: int) -> dict:
    sowing = CROPS[crop]["sowing_months"]
    next_month = month % 12 + 1
    if month in sowing:
        status, label = "now", "Sowing window open now"
    elif next_month in sowing:
        status, label = "now", "Sowing window opens next month"
    else:
        ahead = min((m - month) % 12 for m in sowing)
        upcoming = (month + ahead - 1) % 12 + 1
        status, label = "later", f"Next sowing window: {month_names([upcoming])}"
    return {"status": status, "label": label, "sowing_months": month_names(sowing)}


def _water_check(crop: str, month: int, annual_rain_mm: float, irrigation: bool) -> dict:
    info = CROPS[crop]
    season = SEASON_OF_MONTH[month if month in info["sowing_months"] else
                             next(m for m in sorted(info["sowing_months"], key=lambda m: (m - month) % 12))]
    expected_rain = annual_rain_mm * SEASON_RAIN_SHARE[season] + SEASON_RESIDUAL_MM[season]
    need_min = info["water_mm"][0]
    shortfall = max(0.0, need_min - expected_rain)
    feasible = irrigation or shortfall <= 0.25 * need_min
    return {
        "season": season,
        "need_mm": info["water_mm"],
        "expected_rain_mm": round(expected_rain),
        "feasible_without_irrigation": shortfall <= 0.25 * need_min,
        "feasible": feasible,
    }


# ─── Explanation ──────────────────────────────────────────────────────────────

def _reason(crop: str, score: float, soil: dict, season: dict, water: dict, irrigation: bool) -> str:
    parts = [f"{round(score * 100)}% soil match: Pune soil cards with soil like yours usually list {crop} as suitable"]
    parts.append(f"{ph_class(soil['pH']).lower()} soil (pH {soil['pH']:g}) with "
                 f"{LEVEL_NAMES[rate('OC', soil['OC'])].lower()} organic carbon")
    if season["status"] == "now":
        parts.append(f"its {water['season']} sowing window is open")
    if water["feasible_without_irrigation"]:
        parts.append(f"expected {water['season']} rain + soil moisture (~{water['expected_rain_mm']} mm) "
                     f"covers its water need")
    elif irrigation:
        parts.append(f"needs ~{water['need_mm'][0]} mm water vs ~{water['expected_rain_mm']} mm expected, "
                     f"so it will rely on your irrigation")
    else:
        parts.append(f"needs ~{water['need_mm'][0]} mm water but only ~{water['expected_rain_mm']} mm is expected "
                     f"without irrigation")
    return "; ".join(parts) + "."


def _cost_text(rupees: float) -> str:
    """Indian digit grouping: 3000000 -> ₹30,00,000."""
    digits = str(int(round(rupees)))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return f"₹{digits}"


# ─── Main entry point ─────────────────────────────────────────────────────────

def recommend(soil_raw: dict, area_ha: float, irrigation: bool, on_date: date | None = None) -> dict:
    if _bundle is None:
        raise RuntimeError("Crop model not trained. Run ml/train_crop_model.py first.")

    soil = parse_soil_card(soil_raw)
    month = (on_date or date.today()).month
    annual_rain = district.pune_profile()["mean_rainfall_mm"]

    x = _encode(soil)
    scores = [float(est[0, 1]) if est.shape[1] > 1 else 0.0
              for est in _bundle["model"].predict_proba(x)]
    confidence = _confidence(x, soil)

    results = []
    for crop, score in zip(_bundle["crops"], scores):
        if score < SUITABLE_THRESHOLD:
            continue
        info = CROPS[crop]
        season = _season_status(crop, month)
        water = _water_check(crop, month, annual_rain, irrigation)
        cost_lo, cost_hi = info["cost_per_ha_inr"]
        results.append({
            "crop": crop,
            "marathi": info["marathi"],
            "suitability": round(score, 3),
            "season": season,
            "water": water,
            "water_need": info["water_need"],
            "duration_days": info["duration_days"],
            "harvest_duration": f"{info['duration_days'][0]}–{info['duration_days'][1]} days",
            "cost_per_ha": f"{_cost_text(cost_lo)}–{_cost_text(cost_hi)}",
            "total_cost": f"{_cost_text(cost_lo * area_ha)}–{_cost_text(cost_hi * area_ha)}",
            "reason": _reason(crop, score, soil, season, water, irrigation),
            "fertilizer": fertilizer.advise(crop, soil, area_ha),
        })

    # Crops that can't get enough water are ranked below the ones that can
    def rank_key(r):
        return (not r["water"]["feasible"], -r["suitability"])

    now = sorted([r for r in results if r["season"]["status"] == "now"], key=rank_key)[:TOP_NOW]
    later = sorted([r for r in results if r["season"]["status"] == "later"], key=rank_key)[:TOP_LATER]

    return {
        "soil": soil,
        "soil_levels": {f: LEVEL_NAMES.get(rate(f, soil[f]), rate(f, soil[f]))
                        for f in SOIL_FIELDS if f != "pH"} | {"pH": ph_class(soil["pH"])},
        "confidence": confidence,
        "month": month,
        "sow_now": now,
        "later": later,
        "note": None if results else "No crop in the model scored as suitable for this soil.",
    }


def random_sample_card(rng=None) -> dict:
    """A real Pune soil card from the training data, for demos."""
    import pandas as pd
    from config import PROCESSED_SAMPLES_PATH
    from soil_ratings import BAND_MIDPOINTS

    samples = pd.read_csv(PROCESSED_SAMPLES_PATH)
    row = samples.sample(1, random_state=rng).iloc[0]
    card = {"pH": float(row["pH"]), "OC": float(row["OC"]), "N": float(row["N"])}
    for f in ("P", "K", "S", "Zn", "B", "Fe", "Mn", "Cu"):
        card[f] = BAND_MIDPOINTS[f][row[f]]
    return {
        "soil": card,
        "source": {
            "village": row["village"], "sub_district": row["sub_district"],
            "year": None if pd.isna(row["year"]) else int(row["year"]),
            "known_crops": row["crops"].split(";"),
            "approximated": ["P", "K", "S", "Zn", "B", "Fe", "Mn", "Cu"],
        },
    }
