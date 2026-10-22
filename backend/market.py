"""
Mandi prices and expected profit.

Live prices: data.gov.in "Current Daily Price of Various Commodities from
Various Markets (Mandi)" (Agmarknet), cached for a few hours. Every fetch is
also stored in the database, so the app builds its own price history.

Harvest-month prices: 5 years of Pune-district daily prices downloaded by
ml/fetch_market_history.py. A crop is sold months after sowing, so profit is
estimated from the typical price in its harvest month, not today's price.

Price lookup falls back from Pune-district mandis to the Maharashtra median.
Leafy vegetables are sometimes quoted per 100 bunches instead of per quintal;
those quotes fall below MIN_VALID_PRICE and are dropped.
"""

import json
import statistics
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from functools import lru_cache

import pandas as pd

import database
from config import DATA_GOV_IN_API_KEY, MANDI_HISTORY_PATH, PUNE_YIELDS_PATH
from knowledge import CROPS

LIVE_RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"
HEADERS = {"User-Agent": "Mozilla/5.0 (KisanMitra student project)", "Accept": "application/json"}
CACHE_SECONDS = 6 * 3600
MIN_VALID_PRICE = 150          # Rs/quintal; below this the quote is per bunch, not per quintal
OUTLIER_SHARE = 0.4            # history quotes under 40% of the commodity's median are dropped
MIN_DAYS_PER_YEAR = 5          # a year counts toward the price range only with this many trading days
PADDY_TO_RICE = 0.67           # milled rice per kg of paddy; district statistics report rice
DISTRICT = "Pune"

_lock = threading.Lock()
_live = {"at": 0.0, "records": [], "error": None}


# ─── Live prices ──────────────────────────────────────────────────────────────

LIVE_PAGE = 500


def _fetch_live() -> list[dict]:
    """Today's Maharashtra quotes, fetched in pages (one large request tends to time out)."""
    records, offset = [], 0
    while offset < 10 * LIVE_PAGE:
        params = {"api-key": DATA_GOV_IN_API_KEY, "format": "json", "limit": LIVE_PAGE, "offset": offset,
                  "filters[state.keyword]": "Maharashtra"}
        url = f"https://api.data.gov.in/resource/{LIVE_RESOURCE}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=45) as r:
            page = json.loads(r.read()).get("records", [])
        records += page
        if len(page) < LIVE_PAGE:
            break
        offset += LIVE_PAGE
    return records


def _live_records() -> list[dict]:
    with _lock:
        fresh = time.time() - _live["at"] < CACHE_SECONDS
        if fresh or not DATA_GOV_IN_API_KEY:
            return _live["records"]
    try:
        records = _fetch_live()
        error = None
    except Exception as e:  # keep serving the last good copy
        records, error = None, f"{type(e).__name__}"
    with _lock:
        if records is not None:
            _live.update(at=time.time(), records=records, error=None)
            _store_history(records)
        else:
            _live.update(at=time.time() - CACHE_SECONDS + 600, error=error)  # retry in 10 min
        return _live["records"]


def _store_history(records: list[dict]):
    rows = []
    for r in records:
        try:
            d = "-".join(reversed(r["arrival_date"].split("/")))
            rows.append((d, r["district"], r["market"].strip(), r["commodity"],
                         float(r["min_price"]), float(r["max_price"]), float(r["modal_price"])))
        except (KeyError, ValueError):
            continue
    try:
        database.save_market_prices(rows)
    except Exception as e:  # history is a bonus; never block price lookups
        print(f"[Market] Could not store price history: {e}")


def warm_up():
    """Fetch live prices in the background at startup."""
    threading.Thread(target=_live_records, daemon=True).start()


def _valid(price) -> float | None:
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    return p if p >= MIN_VALID_PRICE else None


def live_price(crop: str) -> dict | None:
    info = CROPS[crop]["market"]
    if info.get("fixed_price_per_quintal"):
        return {"price": info["fixed_price_per_quintal"], "level": "fixed", "basis": info["price_basis"],
                "commodity": "Sugarcane (FRP)", "markets": [], "date": None}
    records = _live_records()
    for name in [info["commodity"], *info.get("alternatives", [])]:
        same = [r for r in records if r.get("commodity") == name and _valid(r.get("modal_price"))]
        for level, pool in (("Pune district", [r for r in same if r.get("district") == DISTRICT]),
                            ("Maharashtra", same)):
            if pool:
                prices = [_valid(r["modal_price"]) for r in pool]
                return {"price": round(statistics.median(prices)), "level": level, "commodity": name,
                        "markets": sorted({r["market"].strip() for r in pool})[:6],
                        "date": max(r["arrival_date"] for r in pool),
                        "basis": f"Median modal price, {len(pool)} quote(s), Agmarknet"}
    return None


def live_status() -> dict:
    with _lock:
        return {"records": len(_live["records"]),
                "fetched": None if not _live["at"] else time.strftime("%d %b %H:%M", time.localtime(_live["at"])),
                "error": _live["error"], "configured": bool(DATA_GOV_IN_API_KEY)}


# ─── Harvest-month prices from history ────────────────────────────────────────

@lru_cache(maxsize=1)
def _history() -> pd.DataFrame | None:
    try:
        h = pd.read_csv(MANDI_HISTORY_PATH, parse_dates=["date"])
    except FileNotFoundError:
        return None
    h = h[h["modal_price"] >= MIN_VALID_PRICE]
    # drop quotes far below a commodity's usual level (other varieties such as broken rice, unit slips)
    typical = h.groupby("commodity")["modal_price"].transform("median")
    h = h[h["modal_price"] >= OUTLIER_SHARE * typical]
    # one price per commodity per day: median across Pune-district markets
    daily = h.groupby(["commodity", "date"], as_index=False)["modal_price"].median()
    daily["month"] = daily["date"].dt.month
    daily["year"] = daily["date"].dt.year
    return daily


def harvest_price(crop: str, harvest_month: int) -> dict | None:
    info = CROPS[crop]["market"]
    if info.get("fixed_price_per_quintal"):
        p = info["fixed_price_per_quintal"]
        return {"median": p, "low": p, "high": p, "commodity": "Sugarcane (FRP)", "years": None,
                "basis": info["price_basis"]}
    h = _history()
    if h is None:
        return None
    for name in [info["commodity"], *info.get("alternatives", [])]:
        m = h[(h["commodity"] == name) & (h["month"] == harvest_month)]
        if len(m) >= 10:
            # typical price per year first, so one volatile year doesn't dominate
            counts = m.groupby("year")["modal_price"].size()
            yearly = m.groupby("year")["modal_price"].median()[counts >= MIN_DAYS_PER_YEAR]
            if yearly.empty:
                continue
            return {"median": round(float(m["modal_price"].median())),
                    "low": round(float(yearly.min())), "high": round(float(yearly.max())),
                    "commodity": name, "years": f"{int(yearly.index.min())}-{int(yearly.index.max())}",
                    "days": int(len(m)),
                    "basis": f"Pune-district mandi prices in {date(2000, harvest_month, 1):%B}, "
                             f"{int(yearly.index.min())}-{int(yearly.index.max())} (Agmarknet)"}
    return None


# ─── Yields and profit ────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _yields() -> dict:
    try:
        y = pd.read_csv(PUNE_YIELDS_PATH)
    except FileNotFoundError:
        return {}
    return {r.crop: {"t_per_ha": float(r.yield_t_per_ha), "years": r.years} for r in y.itertuples()}


def crop_yield(crop: str, commodity: str | None) -> dict | None:
    y = _yields().get(crop)
    if not y:
        return None
    t = y["t_per_ha"]
    note = f"Pune district average {y['years']} (data.gov.in crop statistics)"
    if crop == "Rice" and commodity and commodity.startswith("Paddy"):
        t = round(t / PADDY_TO_RICE, 2)
        note += "; converted from milled rice to paddy"
    return {"t_per_ha": t, "basis": note}


def economics(crop: str, start: date, area_ha: float, fertilizer_cost_per_ha: float) -> dict:
    """Live price, expected harvest price, yield and profit range for one crop."""
    info = CROPS[crop]
    mid_days = sum(info["duration_days"]) / 2
    harvest = start + timedelta(days=mid_days)
    live = live_price(crop)
    expected = harvest_price(crop, harvest.month)
    commodity = (expected or live or {}).get("commodity")
    yld = crop_yield(crop, commodity)
    cost_lo, cost_hi = info["cost_per_ha_inr"]

    out = {"harvest_month": f"{harvest:%b %Y}", "live": live, "expected_price": expected, "yield": yld,
           "cost_per_ha": [cost_lo, cost_hi], "fertilizer_cost_per_ha": round(fertilizer_cost_per_ha),
           "profit_per_ha": None, "profit_total": None, "missing": []}
    if not expected:
        out["missing"].append("harvest-month price history")
    if not yld:
        out["missing"].append("district yield data")
    if expected and yld:
        quintals = yld["t_per_ha"] * 10
        typical = quintals * expected["median"] - (cost_lo + cost_hi) / 2
        low = quintals * expected["low"] - cost_hi
        high = quintals * expected["high"] - cost_lo
        out["profit_per_ha"] = {"low": round(low), "typical": round(typical), "high": round(high)}
        out["profit_total"] = {k: round(v * area_ha) for k, v in out["profit_per_ha"].items()}
        out["income_per_ha_typical"] = round(quintals * expected["median"])
        if crop != "Sugarcane":
            out["yield_note"] = ("District average yield includes rain-fed fields and older years; "
                                 "a well-managed or irrigated field usually yields more.")
    return out
