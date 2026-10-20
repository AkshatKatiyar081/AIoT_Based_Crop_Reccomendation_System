import json
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _load(name: str) -> dict:
    return json.loads((_DIR / name).read_text(encoding="utf-8"))


_crop_kb = _load("crops.json")
CROPS = _crop_kb["crops"]
WATER_CLASSES = _crop_kb["water_classes"]
KB_VERIFIED = _crop_kb["_meta"]["verified"]
TALUKAS = _load("pune_talukas.json")["talukas"]
FERTILIZER_CODES = _load("fertilizer_combinations.json")["codes"]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def month_names(months: list[int]) -> str:
    """[6, 7, 10, 11] -> 'Jun–Jul, Oct–Nov' (groups consecutive months)."""
    if not months:
        return "—"
    months = sorted(months)
    runs, start, prev = [], months[0], months[0]
    for m in months[1:]:
        if m == prev + 1:
            prev = m
            continue
        runs.append((start, prev))
        start = prev = m
    runs.append((start, prev))
    # Join a Dec→Jan wrap-around into one run
    if len(runs) > 1 and runs[0][0] == 1 and runs[-1][1] == 12:
        runs[0] = (runs[-1][0], runs[0][1])
        runs.pop()
    return ", ".join(MONTHS[a - 1] if a == b else f"{MONTHS[a - 1]}–{MONTHS[b - 1]}" for a, b in runs)
