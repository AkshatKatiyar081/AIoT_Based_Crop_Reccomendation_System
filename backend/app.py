import os
import sys

# Ensure backend directory is in path for imports
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, send_from_directory, redirect
from config import SECRET_KEY, PORT
import database
import mqtt_service
from auth import auth_bp
from routes import api_bp

# ─── App factory ──────────────────────────────────────────────────────────────

def create_app():
    app = Flask(__name__, static_folder=None)
    app.secret_key = SECRET_KEY
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(api_bp,  url_prefix="/api")

    # ─── Serve static frontend files ──────────────────────────────────────────
    FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

    @app.route("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.route("/dashboard")
    def dashboard():
        return send_from_directory(FRONTEND_DIR, "dashboard.html")

    @app.route("/css/<path:filename>")
    def serve_css(filename):
        return send_from_directory(os.path.join(FRONTEND_DIR, "css"), filename)

    @app.route("/js/<path:filename>")
    def serve_js(filename):
        return send_from_directory(os.path.join(FRONTEND_DIR, "js"), filename)

    return app


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Kisan Mitra AIoT System")
    print("=" * 60)

    # Initialize database
    database.create_tables()
    print("[DB] Tables ready.")

    # Start MQTT link (falls back to the built-in field simulator when no sensor publishes)
    mqtt_service.start()

    # Create and run app
    app = create_app()
    print(f"[Server] Running at http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
