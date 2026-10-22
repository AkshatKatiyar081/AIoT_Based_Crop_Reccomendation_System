"""
Download Pune-district mandi price history from data.gov.in (Agmarknet,
"Variety-wise Daily Market Prices Data of Commodity") for the project's crops.

Output: data/processed/pune_mandi_prices.csv  (one row per market, commodity, variety and day)

Needs DATA_GOV_IN_API_KEY in backend/.env.
Run:  .venv\\Scripts\\python.exe ml\\fetch_market_history.py [--since 2021-01-01]
"""

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from config import DATA_GOV_IN_API_KEY  # noqa: E402
from knowledge import CROPS  # noqa: E402

RESOURCE = "35985678-0d79-46b4-9ed6-6f13308a1d24"
OUT = ROOT / "data" / "processed" / "pune_mandi_prices.csv"
PAGE = 1000
HEADERS = {"User-Agent": "Mozilla/5.0 (KisanMitra student project)", "Accept": "application/json"}


def fetch_page(commodity: str, offset: int) -> dict:
    params = {
        "api-key": DATA_GOV_IN_API_KEY, "format": "json", "limit": PAGE, "offset": offset,
        "filters[State]": "Maharashtra", "filters[District]": "Pune", "filters[Commodity]": commodity,
        "sort[Arrival_Date]": "desc",
    }
    url = f"https://api.data.gov.in/resource/{RESOURCE}?{urllib.parse.urlencode(params)}"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=120) as r:
                return json.loads(r.read())
        except Exception as e:
            print(f"    retry {attempt + 1} after {type(e).__name__}")
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Could not download {commodity} at offset {offset}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2021-01-01")
    since = date.fromisoformat(ap.parse_args().since)
    if not DATA_GOV_IN_API_KEY:
        sys.exit("Set DATA_GOV_IN_API_KEY in backend/.env first.")

    commodities = sorted({n for c in CROPS.values() for n in [c["market"].get("commodity"), *c["market"].get("alternatives", [])] if n})
    rows = []
    for com in commodities:
        offset, kept = 0, 0
        while True:
            page = fetch_page(com, offset)
            recs = page.get("records", [])
            if not recs:
                break
            stop = False
            for r in recs:
                day = datetime.strptime(r["Arrival_Date"], "%d/%m/%Y").date()
                if day < since:
                    stop = True
                    break
                rows.append({"date": day.isoformat(), "market": r["Market"].strip(), "commodity": com,
                             "variety": r.get("Variety", ""), "min_price": r["Min_Price"],
                             "max_price": r["Max_Price"], "modal_price": r["Modal_Price"]})
                kept += 1
            if stop or len(recs) < PAGE:
                break
            offset += PAGE
        print(f"{com:30} {kept:6} records since {since}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nSaved {len(rows)} rows -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
