import json
from datetime import date, timedelta

from flask import Blueprint, request, jsonify, session

import database
import district
import market
import mqtt_service
import planner
import recommender
import weather
from config import CROP_METRICS_PATH, FERTILIZER_METRICS_PATH
from irrigation import controller
from knowledge import TALUKAS, CROPS, KB_VERIFIED
from soil_ratings import UNITS

api_bp = Blueprint("api", __name__)


def _require_auth():
    """Return user dict if authenticated, else None."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return database.get_user_by_id(user_id)


def _unauthorised():
    return jsonify({"error": "Not authenticated."}), 401


def _taluka(value) -> str:
    return value if value in TALUKAS else "Haveli"


# ─── Reference data ───────────────────────────────────────────────────────────

@api_bp.route("/meta", methods=["GET"])
def meta():
    if not _require_auth():
        return _unauthorised()
    try:
        metrics = json.loads(CROP_METRICS_PATH.read_text(encoding="utf-8"))
        model_eval = metrics["evaluation"]
        model_info = {
            "samples": metrics["dataset"]["unique_soil_samples"],
            "villages": metrics["dataset"]["villages"],
            "top1_correct": model_eval["model"]["top1_correct"]["mean"],
            "precision_at_3": model_eval["model"]["precision_at_3"]["mean"],
            "baseline_top1": model_eval["popularity_baseline"]["top1_correct"]["mean"],
            "method": model_eval["method"],
        }
    except FileNotFoundError:
        model_info = None
    try:
        fert = json.loads(FERTILIZER_METRICS_PATH.read_text(encoding="utf-8"))["evaluation"]
        fert_info = {k: {"accuracy": fert[k]["accuracy"]["mean"],
                         "baseline": fert[k]["crop_majority_baseline_accuracy"]["mean"]}
                     for k in ("combination_1", "combination_2")}
    except FileNotFoundError:
        fert_info = None
    return jsonify({
        "fertilizer_model": fert_info,
        "market": market.live_status(),
        "talukas": [{"name": n, "in_training_data": t["in_training_data"]} for n, t in TALUKAS.items()],
        "soil_units": UNITS,
        "crops": sorted(CROPS),
        "knowledge_base_verified": KB_VERIFIED,
        "model": model_info,
    }), 200


@api_bp.route("/district-profile", methods=["GET"])
def district_profile():
    if not _require_auth():
        return _unauthorised()
    return jsonify(district.pune_profile()), 200


@api_bp.route("/weather", methods=["GET"])
def get_weather():
    if not _require_auth():
        return _unauthorised()
    return jsonify(weather.get_weather(_taluka(request.args.get("taluka")))), 200


@api_bp.route("/soil/sample", methods=["GET"])
def soil_sample():
    if not _require_auth():
        return _unauthorised()
    return jsonify(recommender.random_sample_card()), 200


# ─── Recommendation ───────────────────────────────────────────────────────────

@api_bp.route("/recommend", methods=["POST"])
def recommend():
    if not _require_auth():
        return _unauthorised()

    data = request.get_json() or {}
    try:
        area = float(data.get("area", 1.0))
    except (TypeError, ValueError):
        return jsonify({"error": "Area must be a number."}), 400
    if area <= 0:
        return jsonify({"error": "Area must be greater than 0."}), 400

    try:
        sow_date = date.fromisoformat(data["sowing_date"]) if data.get("sowing_date") else date.today()
    except ValueError:
        return jsonify({"error": "Sowing date must be a valid date."}), 400
    if not date.today() - timedelta(days=60) <= sow_date <= date.today() + timedelta(days=366):
        return jsonify({"error": "Sowing date must be within the last 60 days or the next 12 months."}), 400

    try:
        result = recommender.recommend(
            data.get("soil") or {}, area_ha=area, irrigation=bool(data.get("irrigation")),
            on_date=sow_date, taluka=_taluka(data.get("taluka")),
        )
    except recommender.SoilCardError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    result["taluka"] = _taluka(data.get("taluka"))
    result["area"] = area
    return jsonify(result), 200


@api_bp.route("/plan", methods=["POST"])
def farm_plan():
    """Split the farm into plots and choose a crop for each (expected-profit optimiser)."""
    if not _require_auth():
        return _unauthorised()
    data = request.get_json() or {}
    try:
        total = float(data.get("total_ha"))
        plots = int(data.get("plots"))
        irrigated = float(data.get("irrigated_ha") or 0)
        sow_date = date.fromisoformat(data["sowing_date"]) if data.get("sowing_date") else date.today()
    except (TypeError, ValueError, KeyError):
        return jsonify({"error": "Enter total land, number of plots and irrigated land as numbers."}), 400
    fixed = data.get("fixed") or None
    try:
        soil = recommender.parse_soil_card(data.get("soil") or {})
        result = planner.plan(soil, total, plots, irrigated, sow_date, _taluka(data.get("taluka")), fixed)
    except (recommender.SoilCardError, planner.PlanError) as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(result), 200


@api_bp.route("/recommend/save", methods=["POST"])
def save_recommendation():
    user = _require_auth()
    if not user:
        return _unauthorised()

    data = request.get_json() or {}
    crop_name = data.get("crop_name")
    if crop_name not in CROPS:
        return jsonify({"error": "Unknown crop. Save a crop from the recommendation list."}), 400

    database.add_crop_history(
        user_id=user["id"],
        crop_name=crop_name,
        reason=data.get("reason", ""),
        harvest_duration=data.get("harvest_duration", ""),
        planting_month=data.get("planting_month", ""),
        harvest_month=data.get("harvest_month", ""),
        planting_cost=data.get("planting_cost_per_hectare", ""),
        total_cost=data.get("total_cost", ""),
        taluka=data.get("taluka", ""),
        soil_snapshot=json.dumps(data.get("soil") or {}),
        sowing_date=data.get("sowing_date", ""),
        schedule=json.dumps(data.get("schedule") or {}),
    )
    # The saved crop becomes the irrigation target
    controller.set_crop(crop_name, _taluka(data.get("taluka")))
    return jsonify({"message": "Saved successfully"}), 200


# ─── Sensors and irrigation ───────────────────────────────────────────────────

@api_bp.route("/sensor/latest", methods=["GET"])
def sensor_latest():
    if not _require_auth():
        return _unauthorised()
    return jsonify(mqtt_service.get_status()), 200


@api_bp.route("/irrigation/config", methods=["POST"])
def irrigation_config():
    if not _require_auth():
        return _unauthorised()
    data = request.get_json() or {}
    try:
        if "mode" in data:
            controller.set_mode(data["mode"])
        if "crop" in data or "taluka" in data:
            taluka = _taluka(data.get("taluka", controller.taluka))
            controller.set_crop(data.get("crop", controller.crop), taluka)
            mqtt_service.set_taluka(taluka)
        if "pump" in data:
            controller.set_pump_manual(bool(data["pump"]))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    mqtt_service.publish_pump(controller.pump_on)
    return jsonify(controller.state()), 200


# ─── Upcoming fertilizer tasks ────────────────────────────────────────────────

@api_bp.route("/tasks/upcoming", methods=["GET"])
def upcoming_tasks():
    """Next fertilizer steps across the crops the farmer has saved."""
    user = _require_auth()
    if not user:
        return _unauthorised()
    today = date.today()
    tasks = []
    for row in database.get_crop_history(user["id"]):
        try:
            sched = json.loads(row.get("schedule") or "{}")
        except ValueError:
            continue
        rain = None
        for step in sched.get("steps", []):
            when = date.fromisoformat(step["date"])
            days_left = (when - today).days
            if days_left < -3:          # long past: assume done
                continue
            if rain is None and row.get("taluka"):
                rain = sum((d.get("rain_mm") or 0) for d in weather.get_weather(_taluka(row["taluka"]))["forecast"][:2])
            has_urea = any(p["product"] == "Urea" for p in step.get("products", []))
            warning = (f"{rain:g} mm rain forecast in the next 2 days: delay the urea."
                       if has_urea and rain and rain >= 10 and days_left <= 3 else None)
            tasks.append({"crop": row["crop_name"], "taluka": row.get("taluka"), "date": step["date"],
                          "days_left": days_left, "stage": step["stage"], "products": step.get("products", []),
                          "warning": warning, "history_id": row["id"]})
    tasks.sort(key=lambda t: t["date"])
    return jsonify(tasks[:5]), 200


# ─── Crop History ─────────────────────────────────────────────────────────────

@api_bp.route("/history", methods=["GET"])
def get_history():
    user = _require_auth()
    if not user:
        return _unauthorised()
    return jsonify(database.get_crop_history(user["id"])), 200


@api_bp.route("/history/<int:entry_id>", methods=["DELETE"])
def delete_history(entry_id: int):
    user = _require_auth()
    if not user:
        return _unauthorised()
    if not database.delete_crop_history(entry_id, user["id"]):
        return jsonify({"error": "History entry not found."}), 404
    return jsonify({"message": "Entry deleted."}), 200
