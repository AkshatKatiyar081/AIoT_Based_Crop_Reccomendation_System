"""
Train the two fertilizer-combination models from real Pune Soil Health Card advice.

Inputs (all by Vispute et al., Mendeley Data, CC BY 4.0, same soil cards in the same row order):
  data/pune_mendeley/...      crop advice          (soil card -> crop)
  data/pune_fert_comb/...     fertilizer advice    (soil card + crop -> combination 1 and 2)
  data/pune_organic/...       organic advice       (soil card -> FYM / green manure / ...)

Outputs:
  models/pune_fertilizer_model.joblib   one Random Forest per combination
  models/pune_fertilizer_metrics.json   cross-validation results + organic advice statistics

Soil Health Cards give fertilizer advice per crop, so the models take the soil
card AND the crop as input. Organic advice turned out to be no better than
"always FYM" when modelled, so it's summarised as a rule instead.

Run:  .venv\\Scripts\\python.exe ml\\train_fertilizer_model.py
"""

import json
import sys
from glob import glob
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import dump
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import KFold

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_crop_model import load_raw, encode, FEATURES  # noqa: E402

FERT_GLOB = str(ROOT / "data" / "pune_fert_comb" / "**" / "*.xlsx")
ORGANIC_GLOB = str(ROOT / "data" / "pune_organic" / "**" / "*.xlsx")
MODEL_PATH = ROOT / "models" / "pune_fertilizer_model.joblib"
METRICS_PATH = ROOT / "models" / "pune_fertilizer_metrics.json"

TARGETS = {"combination_1": "F1_Fertilizer Combination1:Advice1",
           "combination_2": "F2_Fertilizer Combination2: Advice2"}
CV_FOLDS = 5
CV_REPEATS = 5


# ─── Load and align ───────────────────────────────────────────────────────────

def load_aligned() -> pd.DataFrame:
    crops = load_raw()  # keeps the original row index of the source sheet
    fert = pd.read_excel(glob(FERT_GLOB, recursive=True)[0])
    organic = pd.read_excel(glob(ORGANIC_GLOB, recursive=True)[0])

    fert = fert.loc[fert.index.intersection(crops.index)]
    organic = organic.loc[organic.index.intersection(crops.index)]
    crops = crops.loc[fert.index]

    # Keep only rows where the three files describe the same soil card
    same = ((fert["Ph"].values == crops["pH"].values)
            & (fert["N"].values == crops["N"].values)
            & (fert["Village"].astype(str).str.strip().values == crops["village"].values)
            & (organic["Ph"].values == crops["pH"].values))
    df = crops[same].copy()
    for name, col in TARGETS.items():
        df[name] = fert.loc[df.index, col].astype(str).str.strip().str.upper()
    df["organic"] = organic.loc[df.index, "Organic Fertilizer Advice"].astype(str).str.strip()
    print(f"Aligned rows: {len(df)} (dropped {int((~same).sum())} rows that didn't match across files)")
    return df


def collapse_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """One row per unique (soil card, crop) pair; label = most common advice for that pair."""
    keys = FEATURES + ["village", "year", "crop"]
    agg = {name: (name, lambda s: s.mode().iloc[0]) for name in TARGETS}
    return df.groupby(keys, dropna=False).agg(**agg).reset_index()


def features_with_crop(pairs: pd.DataFrame, crop_list: list[str]) -> np.ndarray:
    crop_onehot = np.array([[1.0 if c == crop else 0.0 for c in crop_list] for crop in pairs["crop"]])
    return np.hstack([encode(pairs), crop_onehot])


# ─── Evaluation ───────────────────────────────────────────────────────────────

def make_model(seed: int = 42) -> RandomForestClassifier:
    return RandomForestClassifier(n_estimators=300, random_state=seed, n_jobs=-1)


def cross_validate(X, y, crops, groups) -> dict:
    """Grouped by soil profile, so the same soil never appears in train and test."""
    unique_groups = np.unique(groups)
    acc, f1, base = [], [], []
    for repeat in range(CV_REPEATS):
        pred = np.empty(len(y), dtype=object)
        base_pred = np.empty(len(y), dtype=object)
        for tr_g, te_g in KFold(CV_FOLDS, shuffle=True, random_state=repeat).split(unique_groups):
            train = np.isin(groups, unique_groups[tr_g])
            test = ~train
            pred[test] = make_model(repeat).fit(X[train], y[train]).predict(X[test])
            # Baseline: the most common combination for that crop in the training folds
            majority = pd.Series(y[train]).groupby(crops[train]).agg(lambda s: s.mode().iloc[0])
            overall = pd.Series(y[train]).mode().iloc[0]
            base_pred[test] = [majority.get(c, overall) for c in crops[test]]
        acc.append(accuracy_score(y, pred))
        f1.append(f1_score(y, pred, average="macro"))
        base.append(accuracy_score(y, base_pred))

    def s(v):
        return {"mean": round(float(np.mean(v)), 4), "std": round(float(np.std(v)), 4)}
    return {"accuracy": s(acc), "macro_f1": s(f1), "crop_majority_baseline_accuracy": s(base)}


# ─── Organic advice summary (rule, not a model) ───────────────────────────────

def organic_summary(df: pd.DataFrame) -> dict:
    per_soil = df.drop_duplicates(FEATURES + ["village", "year"])
    share = per_soil["organic"].value_counts(normalize=True).round(3).to_dict()
    return {
        "unique_soil_samples": int(len(per_soil)),
        "share": share,
        "most_common": max(share, key=share.get),
        "note": "A Random Forest predicting organic advice scored no better than always answering the "
                "most common value, so the app shows it as a rule.",
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    df = load_aligned()
    pairs = collapse_pairs(df)
    crop_list = sorted(pairs["crop"].unique())
    X = features_with_crop(pairs, crop_list)
    crops = pairs["crop"].to_numpy()
    groups = pd.Series([tuple(r) for r in encode(pairs)]).factorize()[0]
    print(f"Unique (soil, crop) pairs: {len(pairs)}  across {groups.max() + 1} soil profiles")

    models, evaluation, classes = {}, {}, {}
    for name in TARGETS:
        y = pairs[name].to_numpy()
        evaluation[name] = cross_validate(X, y, crops, groups)
        models[name] = make_model().fit(X, y)
        classes[name] = pd.Series(y).value_counts().to_dict()
        e = evaluation[name]
        print(f"\n{name}: {len(classes[name])} classes")
        print(f"  accuracy        {e['accuracy']['mean'] * 100:5.1f}% ± {e['accuracy']['std'] * 100:.1f}")
        print(f"  macro F1        {e['macro_f1']['mean'] * 100:5.1f}%")
        print(f"  crop baseline   {e['crop_majority_baseline_accuracy']['mean'] * 100:5.1f}%")

    organic = organic_summary(df)
    print(f"\nOrganic advice (rule): {organic['share']}")

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    dump({"models": models, "crops": crop_list, "features": FEATURES, "organic": organic}, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps({
        "dataset": {"aligned_rows": int(len(df)), "unique_soil_crop_pairs": int(len(pairs)),
                    "class_counts": classes},
        "evaluation": {"method": f"{CV_REPEATS}x repeated {CV_FOLDS}-fold CV, grouped by soil profile",
                       **evaluation},
        "organic_rule": organic,
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved model   -> {MODEL_PATH.relative_to(ROOT)}")
    print(f"Saved metrics -> {METRICS_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
