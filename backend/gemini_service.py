import json
import re
import time
import google.generativeai as genai
from datetime import datetime
import itertools
from config import GEMINI_API_KEYS, GEMINI_MODEL

key_cycler = itertools.cycle(GEMINI_API_KEYS)

# ─── Offline cost database (realistic Indian farming costs per hectare in INR) ─
CROP_DATA = {
    "rice":        {"cost": 45000, "duration": "120-150 days", "plant": "June",      "harvest": "November"},
    "wheat":       {"cost": 35000, "duration": "120-150 days", "plant": "November",  "harvest": "April"},
    "maize":       {"cost": 30000, "duration": "90-120 days",  "plant": "June",      "harvest": "October"},
    "chickpea":    {"cost": 25000, "duration": "90-120 days",  "plant": "October",   "harvest": "February"},
    "kidneybeans": {"cost": 32000, "duration": "90-120 days",  "plant": "June",      "harvest": "September"},
    "pigeonpeas":  {"cost": 20000, "duration": "150-180 days", "plant": "June",      "harvest": "December"},
    "mothbeans":   {"cost": 18000, "duration": "75-90 days",   "plant": "July",      "harvest": "October"},
    "mungbean":    {"cost": 22000, "duration": "60-90 days",   "plant": "March",     "harvest": "June"},
    "blackgram":   {"cost": 22000, "duration": "80-100 days",  "plant": "July",      "harvest": "October"},
    "lentil":      {"cost": 28000, "duration": "100-120 days", "plant": "October",   "harvest": "March"},
    "pomegranate": {"cost": 150000,"duration": "150-180 days", "plant": "February",  "harvest": "June"},
    "banana":      {"cost": 125000,"duration": "300-365 days", "plant": "June",      "harvest": "Year-round"},
    "mango":       {"cost": 75000, "duration": "150-210 days", "plant": "July",      "harvest": "May"},
    "grapes":      {"cost": 200000,"duration": "150-180 days", "plant": "January",   "harvest": "April"},
    "watermelon":  {"cost": 40000, "duration": "80-100 days",  "plant": "February",  "harvest": "May"},
    "muskmelon":   {"cost": 38000, "duration": "70-90 days",   "plant": "February",  "harvest": "May"},
    "apple":       {"cost": 180000,"duration": "150-180 days", "plant": "January",   "harvest": "August"},
    "orange":      {"cost": 90000, "duration": "240-365 days", "plant": "July",      "harvest": "December"},
    "papaya":      {"cost": 55000, "duration": "270-330 days", "plant": "September", "harvest": "Year-round"},
    "coconut":     {"cost": 60000, "duration": "365+ days",    "plant": "June",      "harvest": "Year-round"},
    "cotton":      {"cost": 42000, "duration": "150-180 days", "plant": "April",     "harvest": "October"},
    "jute":        {"cost": 28000, "duration": "100-120 days", "plant": "March",     "harvest": "July"},
    "coffee":      {"cost": 110000,"duration": "240-300 days", "plant": "June",      "harvest": "November"},
}

_DEFAULT_CROP = {"cost": 35000, "duration": "90-120 days", "plant": "June", "harvest": "October"}


def _get_season(month: int) -> str:
    if month in [12, 1, 2]:
        return "Winter"
    elif month in [3, 4, 5]:
        return "Spring / Pre-Monsoon"
    elif month in [6, 7, 8, 9]:
        return "Monsoon / Kharif Season"
    else:
        return "Post-Monsoon / Rabi Season"


def _format_inr(amount: int) -> str:
    """Format an integer to Indian Rupee style: ₹ 1,25,000"""
    s = str(amount)
    if len(s) <= 3:
        return f"₹ {s}"
    last3 = s[-3:]
    rest = s[:-3]
    groups = []
    while rest:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    return f"₹ {','.join(groups)},{last3}"


def _build_fallback(top_crops: list, area: float) -> list:
    """Build 3 recommendation dicts from ML top crops using the offline cost DB."""
    results = []
    for crop_info in top_crops[:3]:
        name = crop_info["crop"].lower()
        data = CROP_DATA.get(name, _DEFAULT_CROP)
        cost_per_ha = data["cost"]
        total = int(cost_per_ha * area)

        results.append({
            "best_crop":                name.capitalize(),
            "reason":                   f"{name.capitalize()} is well-suited for the current soil conditions "
                                        f"with ML confidence of {crop_info['probability']*100:.1f}%. "
                                        f"It is a proven crop in Indian agriculture with moderate input costs.",
            "harvest_duration":         data["duration"],
            "planting_month":           data["plant"],
            "harvest_month":            data["harvest"],
            "planting_cost_per_hectare": _format_inr(cost_per_ha),
            "total_cost":               _format_inr(total),
        })

    # Pad to 3 if ML gave fewer than 3 crops
    while len(results) < 3:
        results.append({
            "best_crop":                "Rice",
            "reason":                   "Rice is a safe default crop for most Indian regions.",
            "harvest_duration":         "120-150 days",
            "planting_month":           "June",
            "harvest_month":            "November",
            "planting_cost_per_hectare": _format_inr(45000),
            "total_cost":               _format_inr(int(45000 * area)),
        })

    return results


def get_recommendation_with_source(top_crops: list, region: str, crop_history: list, area: float) -> tuple[list, str]:
    """
    Call Gemini API to select the best 3 crops from ML top picks based on cost.
    Falls back to an offline cost database if the API quota is exhausted.
    Implements retry logic with exponential backoff.
    Returns structured list of dicts.
    """

    current_month = datetime.now().month
    current_month_name = datetime.now().strftime("%B")
    season = _get_season(current_month)

    # Build crop list string
    crop_list_str = "\n".join(
        [f"  - {c['crop'].capitalize()} (ML confidence: {c['probability']*100:.1f}%)"
         for c in top_crops]
    )

    # Build history string
    if crop_history:
        history_str = ", ".join(
            [f"{h['crop_name'].capitalize()} (grown on {h['date_recorded'][:10]})"
             for h in crop_history[-5:]]  # Last 5 entries
        )
    else:
        history_str = "No previous crop history."

    prompt = f"""
You are an expert agricultural advisor for Indian farmers.

A farmer in **{region}** needs a crop recommendation for their field of **{area} hectares**.

**Current Date:** {current_month_name} (Month {current_month})
**Season:** {season}

**Top candidate crops predicted by our IoT sensor ML model:**
{crop_list_str}

**Previously grown crops (AVOID these recently grown crops to ensure crop rotation):**
{history_str}

**Your Task:**
1. Select exactly the top 3 best crops from the candidate list above based on suitability and planting cost per hectare. Rank them.
2. For each crop, estimate a realistic planting cost per hectare in INR (₹) and the total cost for {area} hectares.
3. Provide a concise, farmer-friendly explanation (2-3 sentences) for each.
4. Provide the harvest cycle duration in days.
5. Suggest the ideal planting month and expected harvest month.

**IMPORTANT:** Respond ONLY with a valid JSON array of EXACTLY 3 objects in exactly this format — no markdown, no code blocks:
[
  {{
    "best_crop": "<crop name>",
    "reason": "<explanation>",
    "harvest_duration": "<e.g. 90-120 days>",
    "planting_month": "<e.g. June>",
    "harvest_month": "<e.g. October>",
    "planting_cost_per_hectare": "<e.g. ₹ 40,000>",
    "total_cost": "<e.g. ₹ 2,00,000>"
  }},
  ...
]
"""

    # ── Try each API key with exponential backoff retry logic ──
    for key_index, next_key in enumerate(GEMINI_API_KEYS):
        for retry in range(3):  # 3 retries per key
            try:
                genai.configure(api_key=next_key)
                _gemini_model = genai.GenerativeModel(GEMINI_MODEL)

                response = _gemini_model.generate_content(prompt)
                raw_text = response.text.strip()

                # Strip markdown code fences if present
                raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                raw_text = re.sub(r"\s*```$", "", raw_text)

                result_list = json.loads(raw_text)

                # Validate required keys
                required = ["best_crop", "reason", "harvest_duration", "planting_month", "harvest_month", "planting_cost_per_hectare", "total_cost"]
                for result in result_list:
                    for key in required:
                        if key not in result:
                            result[key] = "N/A"

                print(f"[Gemini] Successfully got recommendation from key {key_index + 1}")
                return result_list[:3], "gemini"

            except Exception as e:
                error_msg = str(e).lower()
                if "429" in error_msg or "quota" in error_msg or "resource exhausted" in error_msg:
                    wait_time = min(5 * (2 ** retry), 30)  # Exponential backoff: 5s, 10s, 20s
                    print(f"[Gemini] Key {key_index + 1} rate-limited (retry {retry + 1}/3). Waiting {wait_time}s...")
                    time.sleep(wait_time)
                elif isinstance(e, json.JSONDecodeError):
                    print(f"[Gemini] Key {key_index + 1} JSON decode error: {e}")
                    break  # Move to next key
                else:
                    print(f"[Gemini] Key {key_index + 1} API error (retry {retry + 1}/3): {e}")
                    if retry < 2:
                        time.sleep(2 ** retry)  # Short wait before retry

    # ── Fallback: use offline crop cost database (instant) ──
    print(f"[Gemini] All API keys exhausted. Using offline crop cost database for {len(top_crops)} ML candidates.")
    return _build_fallback(top_crops, area), "fallback_ml"


def get_recommendation(top_crops: list, region: str, crop_history: list, area: float) -> list:
    """Backward-compatible wrapper that returns recommendations only."""
    recommendations, _ = get_recommendation_with_source(top_crops, region, crop_history, area)
    return recommendations
