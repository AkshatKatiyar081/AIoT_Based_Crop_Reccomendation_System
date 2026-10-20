"""
Pune district soil profile from the GIPE Maharashtra dataset
(Vhankade, Harvard Dataverse, doi:10.7910/DVN/QPAW2H, CC BY 4.0).
"""

from functools import lru_cache

import pandas as pd

from config import GIPE_DIR

DISTRICT = "Pune"
FALLBACK_RAINFALL_MM = 931.0


@lru_cache(maxsize=1)
def pune_profile() -> dict:
    try:
        master = pd.read_csv(GIPE_DIR / "master_v3_rainfall.csv")
        cycles = pd.read_csv(GIPE_DIR / "snsi_final.csv")
    except FileNotFoundError:
        return {"available": False, "district": DISTRICT, "mean_rainfall_mm": FALLBACK_RAINFALL_MM}

    row = master[master["district_name"] == DISTRICT].iloc[0]
    trend = cycles[cycles["district_name"] == DISTRICT].sort_values("year")

    def pct(v):
        return None if pd.isna(v) else round(float(v) * 100, 1)

    return {
        "available": True,
        "district": DISTRICT,
        "deficient_share_pct": {
            "Nitrogen": pct(row["def_N"]), "Phosphorus": pct(row["def_P"]),
            "Potassium": pct(row["def_K"]), "Organic carbon": pct(row["def_OC"]),
            "Zinc": pct(row["def_Zn"]),
        },
        "soil_stress": {
            "category": row["stress_category"],
            "index": round(float(row["SNSI"]), 3),
            "by_year": [{"year": r["year"], "index": round(float(r["SNSI"]), 3), "category": r["stress_category"]}
                        for _, r in trend.iterrows()],
        },
        "mean_rainfall_mm": float(row["mean_rainfall"]) if not pd.isna(row["mean_rainfall"]) else FALLBACK_RAINFALL_MM,
        "irrigated_share_pct": pct(row["irrig_share"]),
        "crop_area_share_pct": {
            "Cereals": pct(row["share_cereals"]), "Oilseeds": pct(row["share_oilseeds"]),
            "Pulses": pct(row["share_pulses"]),
        },
        "source": "GIPE Pune, Soil Health Card cycles 2023-24 & 2024-25 (Harvard Dataverse, CC BY 4.0)",
    }
