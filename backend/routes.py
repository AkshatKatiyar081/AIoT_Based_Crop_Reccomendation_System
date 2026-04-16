from flask import Blueprint, request, jsonify, session
import database
import ml_model
import gemini_service
import mqtt_service
import blynk_service


api_bp = Blueprint("api", __name__)


def _require_auth():
    """Return user dict if authenticated, else None."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return database.get_user_by_id(user_id)


# ─── Sensor Data ──────────────────────────────────────────────────────────────

@api_bp.route("/sensor/latest", methods=["GET"])
def get_sensor_data():
    user = _require_auth()
    if not user:
        return jsonify({"error": "Not authenticated."}), 401

    data = mqtt_service.get_latest_sensor_data()
    return jsonify(data), 200


@api_bp.route("/sensor/refresh", methods=["POST"])
def refresh_sensor_data():
    user = _require_auth()
    if not user:
        return jsonify({"error": "Not authenticated."}), 401

    mqtt_service.publish_command("refresh")
    return jsonify({"message": "Refresh command sent"}), 200


# ─── Recommendation ───────────────────────────────────────────────────────────

@api_bp.route("/recommend", methods=["POST"])
def recommend():
    user = _require_auth()
    if not user:
        return jsonify({"error": "Not authenticated."}), 401

    data = request.get_json() or {}
    region = (data.get("region", "")).strip()
    try:
        area = float(data.get("area", 1.0))
    except ValueError:
        area = 1.0

    if not region:
        return jsonify({"error": "Region is required for recommendation."}), 400
    if area <= 0:
        return jsonify({"error": "Area must be greater than 0."}), 400

    # 1. Fetch average sensor data collected over 3.5 seconds
    sensor_data = mqtt_service.get_averaged_sensor_data(duration_seconds=3.5)
    if not sensor_data:
        return jsonify({"error": "No sensor data available. Please ensure the sensor simulator is running."}), 503

    # 2. Get top 5 crops from ML model
    try:
        top_crops = ml_model.get_top_crops(sensor_data, n=5)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    # 3. Fetch user context
    crop_history = database.get_crop_history(user["id"])

    # 4. Call Gemini AI
    try:
        recommendations, recommendation_source = gemini_service.get_recommendation_with_source(
            top_crops, region, crop_history, area=area
        )
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502

    # Push only Gemini-ranked crops to Blynk; avoid pushing ML-fallback ranks as if they were Gemini output.
    if recommendation_source == "gemini":
        blynk_service.push_recommendations(recommendations)
    else:
        blynk_service.push_recommendations([
            {
                "best_crop": "Gemini unavailable",
                "reason": "API rate limit reached. Retry to sync Gemini-ranked crops.",
                "planting_cost_per_hectare": "-",
                "harvest_duration": "-",
            },
            {"best_crop": "-"},
            {"best_crop": "-"},
        ])

    # 5. Return recommendations list directly without auto-saving
    return jsonify({
        "recommendations": recommendations,
        "sensor_data": sensor_data
    }), 200

@api_bp.route("/recommend/save", methods=["POST"])
def save_recommendation():
    user = _require_auth()
    if not user:
        return jsonify({"error": "Not authenticated."}), 401

    data = request.get_json() or {}
    crop_name = data.get("crop_name")
    if not crop_name:
        return jsonify({"error": "Crop name required"}), 400

    database.add_crop_history(
        user_id          = user["id"],
        crop_name        = crop_name,
        reason           = data.get("reason", ""),
        harvest_duration = data.get("harvest_duration", ""),
        planting_month   = data.get("planting_month", ""),
        harvest_month    = data.get("harvest_month", ""),
        planting_cost    = data.get("planting_cost_per_hectare", ""),
        total_cost       = data.get("total_cost", "")
    )
    return jsonify({"message": "Saved successfully"}), 200


# ─── Crop History ─────────────────────────────────────────────────────────────

@api_bp.route("/history", methods=["GET"])
def get_history():
    user = _require_auth()
    if not user:
        return jsonify({"error": "Not authenticated."}), 401

    history = database.get_crop_history(user["id"])
    return jsonify(history), 200


@api_bp.route("/history/<int:entry_id>", methods=["DELETE"])
def delete_history(entry_id: int):
    user = _require_auth()
    if not user:
        return jsonify({"error": "Not authenticated."}), 401

    database.delete_crop_history(entry_id, user["id"])
    return jsonify({"message": "Entry deleted."}), 200
