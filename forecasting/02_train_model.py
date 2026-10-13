"""Section 8.3: train and evaluate one regression model on the splits.

MODEL
    GradientBoostingRegressor (squared error), two configurations sharing
    the same predictor set and the same preprocessing (StandardScaler on
    numeric features, OneHotEncoder on region; both fitted on the usable
    training rows only):
        GB-1  n_estimators=300, learning_rate=0.05, max_depth=3
        GB-2  n_estimators=800, learning_rate=0.02, max_depth=2
    Arbitrary sklearn defaults settle ties in configuration IDs.

PROCEDURE
    1. Load the dataset, apply the lookback exclusion exactly as 8.1 kept
       usable training rows (targets at or after 2026-09-03 00:00 that have
       lag1d and lag2d).
    2. Fit both configurations on the training split.
    3. Score both on the validation split; select the configuration with the
       lowest validation MAE and FREEZE it (its fitted model and fitted
       preprocessing) for all test predictions.
    4. Predict the same 1,680 test hours as the baseline, using only the
       prepared features. No refitting occurs at test time.

OUTPUTS
    - forecasting/model_test_predictions.csv
    - logs/model_training_<CAT timestamp>.txt (validation table + selection)
"""

import json
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from common.cat_time import cat_now, cat_text  # noqa: E402
from common.db import machine_identifier  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402
from forecast_common import FEATURES, load_dataset, metrics  # noqa: E402

EARLIEST_USABLE = pd.Timestamp("2026-09-03T00:00:00+02:00")

CONFIGS = {
    "GB-1": {"n_estimators": 300, "learning_rate": 0.05, "max_depth": 3,
             "subsample": 0.9, "random_state": 0},
    "GB-2": {"n_estimators": 800, "learning_rate": 0.02, "max_depth": 2,
             "subsample": 0.8, "random_state": 0},
}


def make_pipeline(model_params):
    preprocess = ColumnTransformer([
        ("num", StandardScaler(), FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), ["region"]),
    ], remainder="drop")
    return Pipeline([
        ("preprocess", preprocess),
        ("model", GradientBoostingRegressor(**model_params)),
    ])


def main() -> None:
    started = cat_now()
    print("=" * 78)
    print("Section 8.3  Regression model training and evaluation")
    print(f"Started {cat_text()} CAT")
    print(f"Machine {machine_identifier()}")
    print("=" * 78)
    print("")

    rows = load_dataset()
    train = rows[(rows["split"] == "train")
                 & (rows["hour_start"] >= EARLIEST_USABLE)].copy()
    val = rows[rows["split"] == "validation"].copy()
    test = rows[rows["split"] == "test"].copy()

    # Use only rows whose lag features exist (none are missing in practice).
    train = train.dropna(subset=["lag1d", "lag2d", "prev_day_mean"])
    val = val.dropna(subset=["lag1d", "lag2d", "prev_day_mean"])
    test = test.dropna(subset=["lag1d", "lag2d", "prev_day_mean"])

    print(f"  usable training rows     {len(train):,}")
    print(f"  validation rows          {len(val):,}")
    print(f"  test rows                {len(test):,}")
    print("")

    validation_results = []
    fitted = {}
    for config_id, params in CONFIGS.items():
        pipe = make_pipeline(params)
        pipe.fit(train[FEATURES + ["region"]], train["energy_kwh"])
        val_pred = pipe.predict(val[FEATURES + ["region"]])
        m = metrics(val["energy_kwh"], val_pred)
        validation_results.append(
            {"config_id": config_id, "settings": json.dumps(params),
             "train_rows": len(train), "val_rows": len(val),
             "val_MAE": m["MAE"], "val_RMSE": m["RMSE"]}
        )
        fitted[config_id] = pipe
        print(f"  {config_id} trained  validation MAE {m['MAE']:.6f}  "
              f"RMSE {m['RMSE']:.6f}")

    print("")
    print("VALIDATION TABLE (kWh)")
    print(f"  {'Config':<8}{'Train rows':>12}{'Val rows':>10}"
          f"{'Val MAE':>14}{'Val RMSE':>14}")
    for row in validation_results:
        print(f"  {row['config_id']:<8}{row['train_rows']:>12}"
              f"{row['val_rows']:>10}{row['val_MAE']:>14.6f}"
              f"{row['val_RMSE']:>14.6f}")
    print(f"  shared predictors: "
          + ", ".join(FEATURES) + ", region (one-hot)")

    selected = min(validation_results, key=lambda r: r["val_MAE"])
    selected_pipe = fitted[selected["config_id"]]
    print(f"Selected configuration: {selected['config_id']} "
          f"(lowest validation MAE {selected['val_MAE']:.6f} kWh)")
    print("")

    test_pred = selected_pipe.predict(test[FEATURES + ["region"]])
    test_out = test[
        ["hour_start", "region", "energy_kwh"]
    ].rename(columns={"energy_kwh": "actual"})
    test_out["model_pred"] = test_pred
    test_out.to_csv(Path(PROJECT_ROOT) / "forecasting"
                    / "model_test_predictions.csv", index=False)

    m = metrics(test_out["actual"], test_out["model_pred"])
    print("FROZEN MODEL TEST PREDICTIONS (kWh)")
    print(f"  test predictions       {len(test_out):,}")
    print(f"  test MAE               {m['MAE']:.6f}")
    print(f"  test RMSE              {m['RMSE']:.6f}")
    print("")
    print(test_out.head(5).to_string(index=False))
    print("")

    sidecar = {
        "config_id": selected["config_id"],
        "settings": json.loads(selected["settings"]),
        "train_rows": selected["train_rows"],
        "val_rows": selected["val_rows"],
        "val_MAE": selected["val_MAE"],
        "val_RMSE": selected["val_RMSE"],
        "predictors": FEATURES + ["region"],
    }
    (Path(PROJECT_ROOT) / "forecasting"
     / "selected_model_config.json").write_text(
        json.dumps(sidecar, indent=2), encoding="utf-8")
    joblib.dump(
        selected_pipe,
        Path(PROJECT_ROOT) / "forecasting" / "selected_model_pipeline.pkl",
    )
    print("Saved forecasting/selected_model_config.json and "
          "selected_model_pipeline.pkl (frozen)")
    print(f"Completed {cat_text()} CAT")
    print(f"Duration {(cat_now() - started).total_seconds():.3f} s")


if __name__ == "__main__":
    run_with_log("model_training", main)