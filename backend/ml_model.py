import numpy as np
from joblib import load
from config import MODEL_PATH, SCALER_PATH

# Load once at module import
try:
    _model  = load(MODEL_PATH)
    _scaler = load(SCALER_PATH)
    print(f"[ML] Model and scaler loaded successfully.")
except Exception as e:
    _model  = None
    _scaler = None
    print(f"[ML] ERROR loading model/scaler: {e}")


def get_top_crops(sensor_data: dict, n: int = 4) -> list[dict]:
    """
    Scale sensor input and return top-N crops with their probabilities.
    sensor_data keys: N, P, K, temperature, humidity, ph, rainfall
    Returns: [{"crop": "rice", "probability": 0.87}, ...]
    """
    if _model is None or _scaler is None:
        raise RuntimeError("ML model not loaded. Run featurescalling.py first.")

    features = np.array([[
        sensor_data["N"],
        sensor_data["P"],
        sensor_data["K"],
        sensor_data["temperature"],
        sensor_data["humidity"],
        sensor_data["ph"],
        sensor_data["rainfall"],
    ]])

    scaled   = _scaler.transform(features)
    probs    = _model.predict_proba(scaled)[0]
    classes  = _model.classes_

    top_indices = np.argsort(probs)[::-1][:n]
    return [
        {"crop": classes[i], "probability": round(float(probs[i]), 4)}
        for i in top_indices
    ]
