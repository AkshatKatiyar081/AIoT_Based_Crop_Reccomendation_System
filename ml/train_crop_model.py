"""
Train the Pune crop suitability model from real Soil Health Card data.

Input : data/pune_mendeley/.../Cat data all pub.xlsx  (Vispute & Sankhla, CC BY 4.0)
Output: data/processed/pune_soil_samples.csv   cleaned, one row per unique soil sample
        models/pune_crop_model.joblib          model + encoders + reference data
        models/pune_crop_metrics.json          cross-validation results

Each soil card in the source lists several crops, and the source repeats the
card once per crop. We collapse those rows so every soil sample appears once
with its full set of suitable crops, then train a multi-label Random Forest.

Run:  .venv\\Scripts\\python.exe ml\\train_crop_model.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import dump
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import KFold
from sklearn.preprocessing import MultiLabelBinarizer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from soil_ratings import (  # noqa: E402
    BANDS, level_index, NUMERIC_FEATURES, CATEGORICAL_FEATURES, FEATURES,
)

RAW_PATH = ROOT / "data" / "pune_mendeley" / "Soil Nutrient Dataset for Crop Advice" / "Crop Adv data" / "Cat data all pub.xlsx"
PROCESSED_PATH = ROOT / "data" / "processed" / "pune_soil_samples.csv"
MODEL_PATH = ROOT / "models" / "pune_crop_model.joblib"
METRICS_PATH = ROOT / "models" / "pune_crop_metrics.json"

TOP_K = 3
CV_FOLDS = 5
CV_REPEATS = 5


# ─── Load and clean ───────────────────────────────────────────────────────────

def load_raw() -> pd.DataFrame:
    df = pd.read_excel(RAW_PATH)
    df = df.rename(columns={
        "Ph": "pH", "Ph.1": "pH_class", "OC.1": "OC_level", "N.1": "N_level",
        "Crop Advice": "crop", "Sub District": "sub_district", "Village": "village",
        "Year": "year", "District": "district",
    })
    df = df.dropna(subset=["crop"] + FEATURES)
    df[["village", "sub_district"]] = df[["village", "sub_district"]].fillna("Unknown")

    for col in CATEGORICAL_FEATURES + ["crop", "village", "sub_district"]:
        df[col] = df[col].astype(str).str.strip()
    df["crop"] = df["crop"].str.title()
    df["year"] = df["year"].astype("Int64")
    return df


def collapse_to_soil_samples(df: pd.DataFrame) -> pd.DataFrame:
    """One row per unique soil card, with the set of crops advised for it."""
    keys = FEATURES + ["village", "sub_district", "year"]
    grouped = (
        df.groupby(keys, dropna=False)["crop"]
          .apply(lambda s: ";".join(sorted(set(s))))
          .reset_index()
          .rename(columns={"crop": "crops"})
    )
    return grouped


def encode(samples: pd.DataFrame) -> np.ndarray:
    """Numeric features stay numeric; category levels become ordinal integers."""
    X = samples[NUMERIC_FEATURES].astype(float).copy()
    for col in CATEGORICAL_FEATURES:
        X[col] = samples[col].map(lambda lv, c=col: level_index(c, lv))
    return X[FEATURES].to_numpy(dtype=float)


# ─── Evaluation ───────────────────────────────────────────────────────────────

def ranking_scores(Y_true: np.ndarray, scores: np.ndarray, k: int) -> dict:
    top = np.argsort(-scores, axis=1)[:, :k]
    hits = np.take_along_axis(Y_true, top, axis=1)
    n_true = Y_true.sum(axis=1)
    return {
        "top1_correct": float(hits[:, 0].mean()),
        f"any_in_top{k}": float(hits.any(axis=1).mean()),
        f"precision_at_{k}": float(hits.mean(axis=1).mean()),
        f"recall_at_{k}": float((hits.sum(axis=1) / n_true).mean()),
    }


def positive_proba(model, X) -> np.ndarray:
    """predict_proba for a multi-label forest returns one array per crop."""
    cols = []
    for est_proba, classes in zip(model.predict_proba(X), model.classes_):
        if len(classes) == 1:  # crop never/always present in this fold
            cols.append(np.full(len(X), float(classes[0])))
        else:
            cols.append(est_proba[:, list(classes).index(1)])
    return np.column_stack(cols)


def make_model(seed: int = 42) -> RandomForestClassifier:
    return RandomForestClassifier(n_estimators=300, min_samples_leaf=1, random_state=seed, n_jobs=-1)


def cross_validate(X: np.ndarray, Y: np.ndarray, groups: np.ndarray) -> dict:
    """
    Repeated K-fold where identical soil profiles always stay in the same fold,
    so the model is never tested on a soil it has already seen.
    """
    unique_groups = np.unique(groups)
    model_runs, baseline_runs = [], []

    for repeat in range(CV_REPEATS):
        kf = KFold(n_splits=CV_FOLDS, shuffle=True, random_state=repeat)
        model_scores = np.zeros(Y.shape, dtype=float)
        base_scores = np.zeros(Y.shape, dtype=float)

        for train_g, test_g in kf.split(unique_groups):
            train = np.isin(groups, unique_groups[train_g])
            test = ~train
            model = make_model(seed=repeat).fit(X[train], Y[train])
            model_scores[test] = positive_proba(model, X[test])
            # Baseline: always rank crops by how popular they are in training data
            base_scores[test] = Y[train].mean(axis=0)

        model_runs.append(ranking_scores(Y, model_scores, TOP_K))
        baseline_runs.append(ranking_scores(Y, base_scores, TOP_K))

    def summarise(runs):
        return {k: {"mean": round(float(np.mean([r[k] for r in runs])), 4),
                    "std": round(float(np.std([r[k] for r in runs])), 4)} for k in runs[0]}

    return {"model": summarise(model_runs), "popularity_baseline": summarise(baseline_runs)}


# ─── Reference data for the "is this like Pune soil?" check ───────────────────

def build_reference(X: np.ndarray) -> dict:
    mean, std = X.mean(axis=0), X.std(axis=0)
    std[std == 0] = 1.0
    Z = (X - mean) / std
    # Distance from each training sample to its nearest *other* sample
    dists = np.sqrt(((Z[:, None, :] - Z[None, :, :]) ** 2).sum(axis=2))
    np.fill_diagonal(dists, np.inf)
    nn = dists.min(axis=1)
    return {
        "mean": mean, "std": std, "Z": Z,
        "nn_p75": float(np.percentile(nn, 75)),
        "nn_p95": float(np.percentile(nn, 95)),
        "numeric_ranges": {f: (float(X[:, i].min()), float(X[:, i].max()))
                           for i, f in enumerate(FEATURES) if f in NUMERIC_FEATURES},
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    raw = load_raw()
    samples = collapse_to_soil_samples(raw)
    PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    samples.to_csv(PROCESSED_PATH, index=False)

    X = encode(samples)
    crop_sets = samples["crops"].str.split(";")
    mlb = MultiLabelBinarizer()
    Y = mlb.fit_transform(crop_sets)
    groups = pd.Series([tuple(r) for r in X]).factorize()[0]

    print(f"Raw rows: {len(raw)}  ->  unique soil samples: {len(samples)}  "
          f"(unique soil profiles: {groups.max() + 1}), crops: {len(mlb.classes_)}")

    cv = cross_validate(X, Y, groups)
    for name, res in cv.items():
        print(f"\n{name}:")
        for metric, v in res.items():
            print(f"  {metric:<16} {v['mean'] * 100:5.1f}% ± {v['std'] * 100:.1f}")

    final_model = make_model().fit(X, Y)
    importances = dict(sorted(zip(FEATURES, final_model.feature_importances_.round(4).tolist()),
                              key=lambda kv: -kv[1]))

    bundle = {
        "model": final_model,
        "crops": list(mlb.classes_),
        "features": FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "reference": build_reference(X),
        "crop_frequency": dict(zip(mlb.classes_, Y.mean(axis=0).round(4).tolist())),
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    dump(bundle, MODEL_PATH)

    metrics = {
        "dataset": {
            "raw_rows": int(len(raw)),
            "unique_soil_samples": int(len(samples)),
            "unique_soil_profiles": int(groups.max() + 1),
            "crops": list(mlb.classes_),
            "crops_per_sample": samples["crops"].str.count(";").add(1).value_counts().sort_index().to_dict(),
            "villages": sorted(samples["village"].unique().tolist()),
        },
        "evaluation": {
            "method": f"{CV_REPEATS}x repeated {CV_FOLDS}-fold CV, grouped by identical soil profile",
            "top_k": TOP_K,
            **cv,
        },
        "feature_importance": importances,
        "bands_used": {k: v[0] for k, v in BANDS.items()},
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved model   -> {MODEL_PATH.relative_to(ROOT)}")
    print(f"Saved metrics -> {METRICS_PATH.relative_to(ROOT)}")
    print(f"Saved samples -> {PROCESSED_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
