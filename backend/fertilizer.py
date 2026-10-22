"""
Fertilizer advice for one crop on one soil card.

Three parts:
1. Fertilizer combinations: two Random Forests trained on real Pune Soil Health
   Card advice predict which fertilizer combinations the card would list for
   this soil + crop (ml/train_fertilizer_model.py).
2. Doses: the crop's recommended dose (RDF, for medium-fertility soil) is scaled
   by the soil's nutrient rating, the way Soil Health Cards adjust doses
   (Very Low +50%, Low +25%, Medium 100%, High -25%, Very High -50%), then
   converted into a DAP-based and an SSP-based product set.
3. Organic advice: a rule summarising what the soil cards advise.
4. Application schedule: the season's dose split into dated steps (basal +
   top dressings) from each crop's sourced split schedule, with rain warnings.
"""

from datetime import date, timedelta

from joblib import load

from config import FERTILIZER_MODEL_PATH
from knowledge import CROPS, FERTILIZER_CODES
from soil_ratings import rate, ph_class, encode_soil, LEVEL_NAMES

ADJUSTMENT = {"VL": 1.5, "L": 1.25, "M": 1.0, "H": 0.75, "VH": 0.5}

# Nutrient content of fertilizer products (fraction by weight)
UREA_N = 0.46
DAP_N, DAP_P2O5 = 0.18, 0.46
SSP_P2O5 = 0.16
MOP_K2O = 0.60
BAG_KG = {"Urea": 45, "DAP": 50, "SSP": 50, "MOP": 50}

LEGUMES = {"Grams", "Groundnut", "Soybean", "Indian Beans"}

# Card combinations with no potash component (see knowledge/fertilizer_combinations.json)
NO_POTASH_CODES = {"US", "DU", "NU", "NS", "N", "NOT NEEDED"}

# Corrections for deficient secondary/micronutrients (product, kg/ha)
MICRO_FIXES = {
    "Zn": ("Zinc sulphate", 25),
    "S":  ("Bentonite sulphur", 20),
    "B":  ("Borax", 10),
    "Fe": ("Ferrous sulphate", 25),
    "Mn": ("Manganese sulphate", 10),
    "Cu": ("Copper sulphate", 5),
}
MICRO_NAMES = {"Zn": "Zinc", "S": "Sulphur", "B": "Boron", "Fe": "Iron", "Mn": "Manganese", "Cu": "Copper"}

ORGANIC_DOSE = {  # organic carbon level -> (FYM t/ha, vermicompost t/ha)
    "VL": (10, 2.5), "L": (10, 2.5), "M": (7.5, 2.0), "H": (5, 1.5), "VH": (5, 1.5),
}

RAIN_WARN_MM = 10.0   # forecast rain (next 2 days) that would wash urea away
DUE_SOON_DAYS = 3     # a step this close is "due"

try:
    _bundle = load(FERTILIZER_MODEL_PATH)
    print("[ML] Fertilizer combination models loaded.")
except Exception as e:
    _bundle = None
    print(f"[ML] Could not load fertilizer models ({e}). Run ml/train_fertilizer_model.py first.")


def _round5(x: float) -> int:
    return int(5 * round(x / 5))


def _product_rows(amounts: dict, area_ha: float) -> list[dict]:
    rows = []
    for name, per_ha in amounts.items():
        per_ha = _round5(per_ha)
        if per_ha <= 0:
            continue
        total = per_ha * area_ha
        rows.append({"product": name, "kg_per_ha": per_ha, "total_kg": round(total, 1),
                     "bags": round(total / BAG_KG[name], 1), "bag_kg": BAG_KG[name]})
    return rows


# ─── 1. Predicted Soil Health Card combinations ───────────────────────────────

def predict_combinations(crop: str, soil: dict) -> list[dict]:
    if _bundle is None or crop not in _bundle["crops"]:
        return []
    x = [encode_soil(soil) + [1.0 if c == crop else 0.0 for c in _bundle["crops"]]]
    result = []
    for slot, (name, model) in enumerate(_bundle["models"].items(), start=1):
        proba = model.predict_proba(x)[0]
        best = int(proba.argmax())
        code = str(model.classes_[best])
        info = FERTILIZER_CODES.get(code, {"name": f"{code} (unknown code)", "status": "inferred", "dose_option": None})
        result.append({
            "slot": slot, "code": code, "name": info["name"], "status": info["status"],
            "meaning_confidence": info.get("confidence"), "evidence": info.get("evidence") or info.get("note"),
            "dose_option": info["dose_option"], "confidence": round(float(proba[best]), 3),
        })
    return result


# ─── 3. Organic advice (rule) ─────────────────────────────────────────────────

def organic_advice(soil: dict) -> dict:
    stats = _bundle["organic"] if _bundle else {"most_common": "FYM", "share": {"FYM": None}}
    oc_level = rate("OC", soil["OC"])
    fym, vermi = ORGANIC_DOSE[oc_level]
    share = stats["share"].get(stats["most_common"])
    reason = (f"advised on {round(share * 100)}% of Pune soil cards" if share else "most common advice")
    purpose = "to raise" if oc_level in ("VL", "L") else "to maintain"
    return {
        "product": "Farmyard manure (FYM)" if stats["most_common"] == "FYM" else stats["most_common"],
        "reason": reason,
        "text": (f"Apply {fym} t/ha farmyard manure (or {vermi} t/ha vermicompost) before sowing "
                 f"{purpose} organic carbon, which is {LEVEL_NAMES[oc_level].lower()} in your soil."),
    }


# ─── 4. Application schedule ──────────────────────────────────────────────────

def _product(name: str, per_ha: float, area_ha: float) -> dict | None:
    per_ha = int(round(per_ha))
    if per_ha <= 0:
        return None
    total = per_ha * area_ha
    return {"product": name, "kg_per_ha": per_ha, "total_kg": round(total, 1),
            "bags": round(total / BAG_KG[name], 1), "bag_kg": BAG_KG[name]}


def _rain_next_two_days(weather: dict | None) -> float:
    if not weather or not weather.get("forecast"):
        return 0.0
    return round(sum((d.get("rain_mm") or 0) for d in weather["forecast"][:2]), 1)


def application_schedule(crop: str, need: dict, option: str, area_ha: float, start: date,
                         weather: dict | None = None, irrigation: bool = False,
                         today: date | None = None) -> dict:
    """
    Split the season's N, P2O5 and K2O need into dated steps.
    `option` is "dap" (DAP + urea + MOP) or "ssp" (SSP + urea + MOP).
    """
    sched = CROPS[crop]["schedule"]
    today = today or date.today()
    rain = _rain_next_two_days(weather)
    n_credit = 0.0   # N already supplied by DAP beyond a split's own share
    steps = []

    for sp in sched["splits"]:
        n, p, k = need["N"] * sp["N"], need["P2O5"] * sp["P"], need["K2O"] * sp["K"]
        products = []
        if p > 0:
            if option == "dap":
                dap = p / DAP_P2O5
                products.append(_product("DAP", dap, area_ha))
                n -= dap * DAP_N
            else:
                products.append(_product("SSP", p / SSP_P2O5, area_ha))
        if n < 0:                      # DAP brought more N than this split needs
            n_credit += -n
            n = 0.0
        elif n_credit:
            used = min(n, n_credit)
            n, n_credit = n - used, n_credit - used
        if n > 0:
            products.append(_product("Urea", n / UREA_N, area_ha))
        if k > 0:
            products.append(_product("MOP", k / MOP_K2O, area_ha))
        products = [x for x in products if x]

        when = start + timedelta(days=sp["day"])
        days_left = (when - today).days
        status = "done" if days_left < 0 else ("due" if days_left <= DUE_SOON_DAYS else "upcoming")

        tips = []
        has_urea = any(x["product"] == "Urea" for x in products)
        if has_urea and status == "due" and rain >= RAIN_WARN_MM:
            tips.append(f"{rain:g} mm rain is forecast in the next 2 days: wait until it passes, "
                        "or the urea will wash away.")
        if has_urea and sp["day"] > 0:
            tips.append("Spread urea on moist soil, not standing water"
                        + (", then give a light irrigation." if irrigation else ", ideally just before expected light rain."))

        steps.append({
            "day": sp["day"], "date": when.isoformat(), "days_left": days_left, "status": status,
            "stage": sp["stage"],
            "nutrients_kg_per_ha": {"N": round(need["N"] * sp["N"]), "P2O5": round(p), "K2O": round(k)},
            "products": products, "tips": tips,
        })

    return {
        "reference": sched["reference"], "start_date": start.isoformat(), "option": option,
        "option_label": "DAP + Urea + MOP" if option == "dap" else "SSP + Urea + MOP",
        "status": sched["status"], "sources": sched["sources"], "note": sched.get("note"),
        "rain_next_2_days_mm": rain, "steps": steps,
    }


# ─── Main entry point ─────────────────────────────────────────────────────────

def advise(crop: str, soil: dict, area_ha: float, start: date | None = None,
           weather: dict | None = None, irrigation: bool = False) -> dict:
    rdf = CROPS[crop]["rdf"]
    levels = {n: rate(n, soil[n]) for n in ("N", "P", "K")}

    need_n = rdf["N"] * ADJUSTMENT[levels["N"]]
    need_p = rdf["P2O5"] * ADJUSTMENT[levels["P"]]
    need_k = rdf["K2O"] * ADJUSTMENT[levels["K"]]
    mop = need_k / MOP_K2O

    # 2. Two ways to supply the same nutrients
    dap = need_p / DAP_P2O5
    dap_option = {"Urea": max(0.0, need_n - dap * DAP_N) / UREA_N, "DAP": dap, "MOP": mop}
    ssp_option = {"Urea": need_n / UREA_N, "SSP": need_p / SSP_P2O5, "MOP": mop}

    combinations = predict_combinations(crop, soil)
    # Only claim a match when a predicted combination actually names those products
    preferred = next((c["dose_option"] for c in combinations if c["dose_option"]), None)

    dose_options = [
        {"id": "dap", "label": "DAP + Urea + MOP", "products": _product_rows(dap_option, area_ha),
         "matches_card": preferred == "dap"},
        {"id": "ssp", "label": "SSP + Urea + MOP", "products": _product_rows(ssp_option, area_ha),
         "matches_card": preferred == "ssp",
         "note": "SSP also supplies about 12% sulphur."},
    ]
    dose_options.sort(key=lambda o: not o["matches_card"])

    notes = []
    if need_k > 0 and combinations and all(c["code"] in NO_POTASH_CODES for c in combinations):
        notes.append("The Soil Health Card combinations predicted for this soil contain no potash, so the MOP "
                     "above can likely be skipped. Follow your own card if it says otherwise.")
    if crop in LEGUMES:
        notes.append("Pulse/oilseed legume: treat seed with Rhizobium + PSB culture; it fixes part of its own nitrogen.")
    if soil["pH"] <= 5.5:
        notes.append("Soil is strongly acidic: apply agricultural lime based on a lime requirement test.")
    elif soil["pH"] > 8.5:
        notes.append("Soil is strongly alkaline: apply gypsum based on a gypsum requirement test.")

    micro = []
    for nut, (product, kg) in MICRO_FIXES.items():
        if rate(nut, soil[nut]) == "L":
            micro.append({"nutrient": MICRO_NAMES[nut], "product": product,
                          "kg_per_ha": kg, "total_kg": round(kg * area_ha, 1)})

    need = {"N": need_n, "P2O5": need_p, "K2O": need_k}
    schedule = application_schedule(crop, need, dose_options[0]["id"], area_ha, start or date.today(),
                                     weather=weather, irrigation=irrigation)

    return {
        "crop": crop,
        "schedule": schedule,
        "soil_status": {
            "N": LEVEL_NAMES[levels["N"]], "P": LEVEL_NAMES[levels["P"]], "K": LEVEL_NAMES[levels["K"]],
            "OC": LEVEL_NAMES[rate("OC", soil["OC"])], "pH": ph_class(soil["pH"]),
        },
        "nutrient_need_kg_per_ha": {"N": round(need_n), "P2O5": round(need_p), "K2O": round(need_k)},
        "standard_dose_kg_per_ha": rdf,
        "card_combinations": combinations,
        "dose_options": dose_options,
        "micronutrients": micro,
        "organic": organic_advice(soil),
        "notes": notes,
    }
