# Kisan Mitra AIoT Crop Recommendation System

An AIoT project that combines:
- IoT-style sensor data (real MQTT or simulator)
- ML-based crop prediction
- Gemini-assisted recommendation ranking
- Web dashboard for farmers

## Project Structure

- `backend/` Flask API, auth, DB, MQTT, Gemini, Blynk integration
- `frontend/` login and dashboard pages (HTML/CSS/JS)
- `sensor_simulator.py` publishes simulated sensor readings to MQTT
- `wokwi/` embedded simulation project (PlatformIO/Wokwi)
- `crop_model.joblib`, `scaler.joblib` trained ML artifacts

## Prerequisites

- Python 3.10+
- (Optional) PlatformIO for `wokwi/`

## Setup

1. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install backend dependencies:

```powershell
pip install -r backend/requirements.txt
```

3. Configure environment variables:

- Copy `backend/.env.example` to `backend/.env`
- Fill in your own secrets and API credentials

## Run Locally

1. Start backend:

```powershell
python backend/app.py
```

2. In another terminal, run simulator (optional if using real device MQTT data):

```powershell
python sensor_simulator.py
```

3. Open:

- `http://localhost:5000/` (login)
- `http://localhost:5000/dashboard` (dashboard)

## Security Notes

- Do not commit real API keys, broker passwords, or Blynk tokens.
- Keep `backend/.env` private (already ignored by `.gitignore`).
- If secrets were committed earlier, rotate them before publishing.

## Suggested First Push Workflow

```powershell
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```
