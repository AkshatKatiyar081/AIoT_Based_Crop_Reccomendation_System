"""
Average Pune-district crop yields from data.gov.in
("District-wise, season-wise crop production statistics from 1997").

The dataset ends in 2014, so yields are averaged over the last five years it
covers (2010-2014) and labelled as such. Area is in hectares, production in
tonnes (sugarcane in tonnes of cane).

Output: data/processed/pune_crop_yields.csv
Run:    .venv\\Scripts\\python.exe ml\\fetch_pune_yields.py
"""

import csv
import json
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from config import DATA_GOV_IN_API_KEY  # noqa: E402

RESOURCE = "35be999b-0208-4354-b557-f6ca9a5355de"
OUT = ROOT / "data" / "processed" / "pune_crop_yields.csv"
YEARS = range(2010, 2015)
HEADERS = {"User-Agent": "Mozilla/5.0 (KisanMitra student project)", "Accept": "application/json"}

# Our crop name -> crop name in the production dataset
CROP_NAMES = {
    "Rice": "Rice", "Wheat": "Wheat", "Jowar": "Jowar", "Bajra": "Bajra", "Grams": "Gram",
    "Groundnut": "Groundnut", "Maize": "Maize", "Soybean": "Soyabean", "Ragi": "Ragi", "Sugarcane": "Sugarcane",
}


def main():
    params = {"api-key": DATA_GOV_IN_API_KEY, "format": "json", "limit": 1000,
              "filters[state_name]": "Maharashtra", "filters[district_name]": "PUNE"}
    url = f"https://api.data.gov.in/resource/{RESOURCE}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=120) as r:
        records = json.loads(r.read())["records"]

    area, prod, seen_years = defaultdict(float), defaultdict(float), defaultdict(set)
    for r in records:
        if r["crop_year"] not in YEARS:
            continue
        try:
            a, p = float(r["area_"]), float(r["production_"])
        except (TypeError, ValueError):
            continue          # "NA" production
        for ours, theirs in CROP_NAMES.items():
            if r["crop"] == theirs:
                area[ours] += a
                prod[ours] += p
                seen_years[ours].add(r["crop_year"])

    rows = []
    for crop in CROP_NAMES:
        if area[crop] > 0:
            rows.append({"crop": crop, "yield_t_per_ha": round(prod[crop] / area[crop], 2),
                         "years": f"{min(seen_years[crop])}-{max(seen_years[crop])}",
                         "area_ha_total": int(area[crop])})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(f"{r['crop']:10} {r['yield_t_per_ha']:7} t/ha  ({r['years']}, {r['area_ha_total']:,} ha)")
    print(f"Saved -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
