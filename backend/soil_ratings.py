"""
Soil test ratings used to turn Soil Health Card numbers into categories.

The same bands are used for training (ml/train_crop_model.py) and at runtime,
so a farmer's numeric soil card lines up with the categorical Pune dataset.

N and OC bands were checked against the numeric + category columns in the
Pune Mendeley dataset (they match exactly). P and K follow the same
Maharashtra 6-class rating with "moderately high" merged into "medium",
which is how the dataset collapses N. Micronutrient bands are the standard
DTPA critical limits printed on Soil Health Cards.
"""

# Ordered 5-level and 3-level scales
LEVELS_5 = ["VL", "L", "M", "H", "VH"]
LEVELS_3 = ["L", "M", "H"]

LEVEL_NAMES = {
    "VL": "Very Low", "L": "Low", "M": "Medium", "H": "High", "VH": "Very High",
}

# Upper bound (inclusive) of each band; anything above the last bound is the top band
BANDS = {
    #       VL     L      M      H      (VH above)
    "N":  ([140,   280,   560,   700],  LEVELS_5),   # kg/ha available N
    "P":  ([7,     14,    28,    35],   LEVELS_5),   # kg/ha available P
    "K":  ([100,   150,   250,   300],  LEVELS_5),   # kg/ha available K
    "OC": ([0.24,  0.50,  0.75,  1.00], LEVELS_5),   # % organic carbon
    #       L      M      (H above)
    "S":  ([10,    20],                 LEVELS_3),   # ppm
    "Zn": ([0.6,   1.2],                LEVELS_3),   # ppm
    "B":  ([0.5,   1.0],                LEVELS_3),   # ppm
    "Fe": ([4.5,   9.0],                LEVELS_3),   # ppm
    "Mn": ([2.0,   4.0],                LEVELS_3),   # ppm
    "Cu": ([0.2,   0.4],                LEVELS_3),   # ppm
}

# A representative value inside each band, used when only the category is known
# (e.g. loading a sample card from the categorical Pune dataset)
BAND_MIDPOINTS = {
    "P":  {"VL": 5,   "L": 11,  "M": 21,  "H": 32,  "VH": 45},
    "K":  {"VL": 80,  "L": 125, "M": 200, "H": 275, "VH": 350},
    "S":  {"L": 7,    "M": 15,  "H": 28},
    "Zn": {"L": 0.4,  "M": 0.9, "H": 1.6},
    "B":  {"L": 0.35, "M": 0.75, "H": 1.3},
    "Fe": {"L": 3.0,  "M": 6.5, "H": 12.0},
    "Mn": {"L": 1.4,  "M": 3.0, "H": 6.0},
    "Cu": {"L": 0.15, "M": 0.3, "H": 0.6},
}

# Units shown in the UI
UNITS = {
    "pH": "", "OC": "%", "N": "kg/ha", "P": "kg/ha", "K": "kg/ha",
    "S": "ppm", "Zn": "ppm", "B": "ppm", "Fe": "ppm", "Mn": "ppm", "Cu": "ppm",
}

# Values outside these limits are physically implausible on a soil card
PLAUSIBLE = {
    "pH": (3.0, 11.0), "OC": (0.0, 5.0), "N": (0, 2000), "P": (0, 300), "K": (0, 2000),
    "S": (0, 200), "Zn": (0, 50), "B": (0, 20), "Fe": (0, 300), "Mn": (0, 300), "Cu": (0, 50),
}


def rate(nutrient: str, value: float) -> str:
    """Return the rating code (VL/L/M/H/VH) for a numeric soil value."""
    bounds, levels = BANDS[nutrient]
    for bound, level in zip(bounds, levels):
        if value <= bound:
            return level
    return levels[-1]


def level_index(nutrient: str, level: str) -> int:
    """Ordinal position of a level within the nutrient's scale (0 = lowest)."""
    return BANDS[nutrient][1].index(level)


# Model input order shared by every model (training and runtime)
NUMERIC_FEATURES = ["pH", "OC", "N"]
CATEGORICAL_FEATURES = ["P", "K", "S", "Zn", "B", "Fe", "Mn", "Cu"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def encode_soil(soil: dict) -> list[float]:
    """Numeric soil card -> model features (numbers for pH/OC/N, band index for the rest)."""
    row = [float(soil[f]) for f in NUMERIC_FEATURES]
    row += [level_index(f, rate(f, soil[f])) for f in CATEGORICAL_FEATURES]
    return row


def ph_class(ph: float) -> str:
    """pH description using the same classes as the Pune dataset."""
    if ph <= 5.5:
        return "Highly acidic"
    if ph <= 6.5:
        return "Moderately acidic"
    if ph < 7.0:
        return "Slightly acidic"
    if ph == 7.0:
        return "Neutral"
    if ph <= 8.5:
        return "Moderately alkaline"
    return "Strongly alkaline"
