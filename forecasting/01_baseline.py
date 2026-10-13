"""Section 8.2: evaluate the previous-day baseline.

Baseline definition (Section 8.2.1): at 00:00 CAT on each test day the 24
hourly values of that day are forecast using the previous day's corresponding
hourly consumption. Because the dataset stores observed consumption per
(region, CAT hour), the baseline prediction for target hour H is simply the
observed value of hour H-24h (lag1d), which was already available at 00:00.

Coverage: 10 regions x 7 test days x 24 hours = 1,680 test predictions.
Metrics: MAE and RMSE in kWh over all 1,680 observations, and per region.

OUTPUTS
    - forecasting/baseline_test_predictions.csv
    - logs/baseline_<CAT timestamp>.txt
"""

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from common.cat_time import cat_now, cat_text  # noqa: E402
from common.db import machine_identifier  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402
from forecast_common import load_dataset, metrics  # noqa: E402


def main() -> None:
    started = cat_now()
    print("=" * 78)
    print("Section 8.2  Previous-day baseline evaluation")
    print(f"Started {cat_text()} CAT")
    print(f"Machine {machine_identifier()}")
    print("=" * 78)
    print("")

    rows = load_dataset()
    test = rows[rows["split"] == "test"].copy()

    # Baseline = observed value 24 hours earlier (available at 00:00).
    test["baseline_pred"] = test["lag1d"]

    predictions = test[
        ["hour_start", "region", "energy_kwh", "baseline_pred"]
    ].rename(columns={"energy_kwh": "actual"})
    predictions.to_csv(Path(PROJECT_ROOT) / "forecasting"
                       / "baseline_test_predictions.csv", index=False)

    actual = predictions["actual"].values
    predicted = predictions["baseline_pred"].values
    overall = metrics(actual, predicted)

    print(f"  test predictions        {len(predictions):,}")
    print(f"  actual hours            {predictions['hour_start'].nunique():,}"
          " per region")
    print(f"  regions                 {predictions['region'].nunique()}")
    print("")
    print("OVERALL (all 1,680 test observations, kWh)")
    print(f"  MAE   {overall['MAE']:.6f} kWh")
    print(f"  RMSE  {overall['RMSE']:.6f} kWh")
    print("")
    print("  sample predictions (first 5 test rows)")
    print(predictions.head(5).to_string(index=False))
    print("")
    print("PER-REGION BASELINE METRICS (kWh)")
    print(f"  {'Region':<12}{'MAE':>14}{'RMSE':>14}")
    for region, group in predictions.groupby("region", sort=False):
        m = metrics(group["actual"], group["baseline_pred"])
        print(f"  {region:<12}{m['MAE']:>14.6f}{m['RMSE']:>14.6f}")
    print("")
    print(f"Predictions saved to "
          "forecasting/baseline_test_predictions.csv")
    print(f"Completed {cat_text()} CAT")
    print(f"Duration {(cat_now() - started).total_seconds():.3f} s")


if __name__ == "__main__":
    run_with_log("baseline", main)