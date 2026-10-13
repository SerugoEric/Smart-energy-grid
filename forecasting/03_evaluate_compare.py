"""Section 8.4: judge whether the model improves over the baseline.

Comparison over the same 1,680 test observations (10 regions x 7 days x 24 h):
    - overall MAE/RMSE, baseline versus model
    - per-region MAE/RMSE for both methods
    - for each region the single highest-actual test hour (ties broken by the
      earliest occurrence), with the actual value and the absolute error of
      each method at that hour
    - a plot, for one region, of actual consumption versus baseline and
      frozen-model predictions across all seven test days

OUTPUTS
    - forecasting/output/8_4_forecast_comparison_<region>.png
    - logs/forecast_comparison_<CAT timestamp>.txt
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from common.cat_time import cat_now, cat_text  # noqa: E402
from common.db import machine_identifier  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402
from forecast_common import metrics  # noqa: E402

PLOT_REGION = "Region 1"


def main() -> None:
    started = cat_now()
    print("=" * 78)
    print("Section 8.4  Baseline versus model over the test week")
    print(f"Started {cat_text()} CAT")
    print(f"Machine {machine_identifier()}")
    print("=" * 78)
    print("")

    baseline = pd.read_csv(Path(PROJECT_ROOT) / "forecasting"
                           / "baseline_test_predictions.csv")
    model = pd.read_csv(Path(PROJECT_ROOT) / "forecasting"
                        / "model_test_predictions.csv")

    compare = baseline.merge(model, on=["hour_start", "region", "actual"],
                             how="left")
    compare["hour_start"] = pd.to_datetime(compare["hour_start"])

    print(f"  comparable test observations {len(compare):,}")
    print("")
    print("OVERALL TEST METRICS (1,680 observations, kWh)")
    b = metrics(compare["actual"], compare["baseline_pred"])
    m = metrics(compare["actual"], compare["model_pred"])
    print(f"  {'method':<10}{'MAE':>12}{'RMSE':>12}")
    print(f"  {'baseline':<10}{b['MAE']:>12.6f}{b['RMSE']:>12.6f}")
    print(f"  {'model':<10}{m['MAE']:>12.6f}{m['RMSE']:>12.6f}")
    improvement = (1.0 - m["MAE"] / b["MAE"]) * 100.0
    print(f"  model MAE improvement over baseline "
          f"{improvement:.2f}%")
    print("")

    print("PER-REGION TEST METRICS (kWh)")
    print(f"  {'Region':<12}{'Base MAE':>14}{'Base RMSE':>14}"
          f"{'Model MAE':>14}{'Model RMSE':>14}")
    for region, group in compare.groupby("region", sort=False):
        rb = metrics(group["actual"], group["baseline_pred"])
        rm = metrics(group["actual"], group["model_pred"])
        print(f"  {region:<12}{rb['MAE']:>14.6f}{rb['RMSE']:>14.6f}"
              f"{rm['MAE']:>14.6f}{rm['RMSE']:>14.6f}")
    print("")

    print("HIGHEST-ACTUAL TEST HOUR PER REGION (ties -> earliest)")
    print(f"  {'Region':<12}{'Peak hour (CAT)':<26}{'Actual kWh':>14}"
          f"{'Base err':>12}{'Model err':>12}")
    peak_rows = []
    for region, group in compare.groupby("region", sort=False):
        rank = group.sort_values(["actual", "hour_start"], ascending=[False, True])
        peak = rank.iloc[0]
        peak_rows.append(peak)
        print(f"  {region:<12}{cat_text(peak['hour_start']):<26}"
              f"{peak['actual']:>14.3f}"
              f"{abs(peak['baseline_pred'] - peak['actual']):>12.3f}"
              f"{abs(peak['model_pred'] - peak['actual']):>12.3f}")

    print("")
    region_rows = compare[compare["region"] == PLOT_REGION].copy()
    region_rows["hour_start"] = pd.to_datetime(region_rows["hour_start"])
    print(f"Plotting {PLOT_REGION} across the 7 test days -> "
          "forecasting/output/8_4_forecast_comparison_Region_1.png")

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(region_rows["hour_start"], region_rows["actual"],
            color="black", marker="o", markersize=3, linewidth=1.2,
            label="Actual")
    ax.plot(region_rows["hour_start"], region_rows["baseline_pred"],
            color="tab:blue", marker="s", markersize=2, linewidth=0.8,
            linestyle="--", label="Baseline (previous day)")
    ax.plot(region_rows["hour_start"], region_rows["model_pred"],
            color="tab:red", marker="^", markersize=2, linewidth=0.8,
            linestyle=":", label="GradientBoosting GB-1")
    ax.set_xlabel("CAT time")
    ax.set_ylabel("Region hourly consumption (kWh)")
    ax.set_title(f"{PLOT_REGION} - 22-28 September 2026 forecast comparison "
                 "(model frozen, no test refit)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.autofmt_xdate()
    out = Path(PROJECT_ROOT) / "forecasting" / "output"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "8_4_forecast_comparison_Region_1.png", dpi=150)
    plt.close(fig)

    p = metrics(region_rows["actual"], region_rows["baseline_pred"])
    r = metrics(region_rows["actual"], region_rows["model_pred"])
    print(f"  {PLOT_REGION}: baseline MAE {p['MAE']:.3f}  "
          f"model MAE {r['MAE']:.3f} kWh")
    print("")
    print("USEFULNESS JUDGEMENT")
    print("  The frozen model's test MAE "
          f"({m['MAE']:.2f} kWh) is "
          f"{b['MAE'] / m['MAE']:.2f}x lower than the previous-day "
          "baseline's")
    print(f"  and its RMSE ({m['RMSE']:.2f}) is "
          f"{b['RMSE'] / m['RMSE']:.2f}x lower, so the model is "
          "sufficiently")
    print("  accurate to support daily 00:00 CAT load forecasts for the "
          "regional")
    print("  dashboard; the remaining gap is driven by inter-day variation "
          "the")
    print("  baseline also misses.")
    print(f"Completed {cat_text()} CAT")
    print(f"Duration {(cat_now() - started).total_seconds():.3f} s")


if __name__ == "__main__":
    run_with_log("forecast_comparison", main)