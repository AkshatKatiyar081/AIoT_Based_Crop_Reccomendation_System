from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
import database

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()

    name      = (data.get("name", "") or "").strip()
    email     = (data.get("email", "") or "").strip().lower()
    password  = data.get("password", "") or ""

    if not all([name, email, password]):
        return jsonify({"error": "Name, email, and password are required."}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400

    password_hash = generate_password_hash(password)
    user_id = database.add_user(name, email, password_hash, "", "")

    if user_id is None:
        return jsonify({"error": "An account with this email already exists."}), 409

    session["user_id"] = user_id
    return jsonify({"message": "Registration successful.", "user_id": user_id}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    email    = (data.get("email", "") or "").strip().lower()
    password = data.get("password", "") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    user = database.get_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password."}), 401

    session["user_id"] = user["id"]
    return jsonify({
        "message": "Login successful.",
        "user": {
            "id":        user["id"],
            "name":      user["name"],
            "email":     user["email"],
            "region":    user["region"],
            "soil_type": user["soil_type"],
        }
    }), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully."}), 200


@auth_bp.route("/me", methods=["GET"])
def me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated."}), 401

    user = database.get_user_by_id(user_id)
    if not user:
        session.clear()
        return jsonify({"error": "User not found."}), 404

    return jsonify({
        "id":        user["id"],
        "name":      user["name"],
        "email":     user["email"],
        "region":    user["region"],
        "soil_type": user["soil_type"],
    }), 200
