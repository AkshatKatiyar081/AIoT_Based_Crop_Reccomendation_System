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
"""

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


# ─── Main entry point ─────────────────────────────────────────────────────────

def advise(crop: str, soil: dict, area_ha: float) -> dict:
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
    if need_n > 0:
        notes.append("Apply all phosphorus and potash fertilizer and half the urea at sowing; "
                     "give the remaining urea 30–45 days later.")
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

    return {
        "crop": crop,
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
