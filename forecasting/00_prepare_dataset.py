"""Section 8.1: prepare the chronological hourly regional dataset and features.

DATASET
    One row per (region, CAT hour) over the whole historical period, built
    from the Section 6.1 hourly regional continuous aggregate
    (cagg_hour_region). sum_energy_kwh is the observed total for that hour
    and region and is preserved exactly as the evaluation target; the reading
    count for the hour is carried along so absent hours can be reported.

SPLITS  (by target timestamp; Section 8.1.2)
    train      1 September 00:00 .. 15 September 00:00 (exclusive)
    validation 15 September 00:00 .. 22 September 00:00
    test       22 September 00:00 .. 29 September 00:00

FEATURES (Section 8.1.3)
    For a target hour on day D, the forecast origin is 00:00 CAT on day D,
    so only same-day information up to 00:00 and everything on earlier days
    may be used. The features used here:
        lag1d         consumption 24 h earlier (previous day, same hour)
        lag2d         consumption 48 h earlier
        prev_day_mean average consumption of the 24 hours of the previous
                      CAT day; changing values cannot appear within the
                      forecast day
        hour          CAT hour of the target (calendar)
        day_of_week   weekday index 0..6, Monday first (calendar)
        is_weekend    1 for Saturday/Sunday
        day_index     days since 1 September (steady trend)
        region        one-hot encoded, fit on the training split only
    earliest usable target = max feature lookback (48 h) => 3 September 00:00.

    Training rows that lack the initial lookback (targets on 1-2 September,
    i.e. before 3 September 00:00) are excluded. The SAME usable training
    rows feed every model configuration.

OUTPUTS
    - data/forecast_dataset.csv  (one row per region and CAT hour)
    - data/forecast_dataset.parquet
    - logs/forecast_dataset_<CAT timestamp>.txt  split sizes, feature table,
      lookback exclusions, missing-hour report
"""

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from common.cat_time import cat_now, cat_text  # noqa: E402
from common.db import connect, machine_identifier  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402

TRAIN_START = datetime.fromisoformat("2026-09-01T00:00:00+02:00")
VAL_START = datetime.fromisoformat("2026-09-15T00:00:00+02:00")
TEST_START = datetime.fromisoformat("2026-09-22T00:00:00+02:00")
TEST_END = datetime.fromisoformat("2026-09-29T00:00:00+02:00")


def main() -> None:
    started = cat_now()
    print("=" * 78)
    print("Section 8.1  Chronological hourly dataset and features")
    print(f"Started {cat_text()} CAT")
    print(f"Machine {machine_identifier()}")
    print("=" * 78)
    print("")

    connection = connect()
    rows = pd.read_sql_query(
        """
        SELECT bucket AS hour_start, region,
               sum_energy_kwh AS energy_kwh,
               reading_count
        FROM cagg_hour_region
        ORDER BY region, bucket
        """,
        connection,
    )
    connection.close()

    print("SOURCE CAGG cagg_hour_region")
    print(f"  raw rows read        {len(rows):,}")
    print(f"  regions              {sorted(rows['region'].unique())}")
    print("")

    # calendar features --------------------------------------------------
    rows["day"] = rows["hour_start"].dt.normalize()
    rows["hour"] = rows["hour_start"].dt.hour
    rows["day_of_week"] = rows["hour_start"].dt.dayofweek
    rows["is_weekend"] = (rows["day_of_week"] >= 5).astype(int)
    rows["day_index"] = (rows["day"]
                         - pd.Timestamp("2026-09-01", tz="+02:00")).dt.days

    # lag and window features --------------------------------------------
    rows = rows.sort_values(["region", "hour_start"]).reset_index(drop=True)
    rows["lag1d"] = rows.groupby("region")["energy_kwh"].shift(24)
    rows["lag2d"] = rows.groupby("region")["energy_kwh"].shift(48)

    day_totals = (rows.groupby(["region", "day"], as_index=False)
                  ["energy_kwh"].sum())
    day_totals["prev_day_total"] = (
        day_totals.groupby("region")["energy_kwh"].shift(1)
    )
    rows = rows.merge(day_totals[["region", "day", "prev_day_total"]],
                      on=["region", "day"], how="left")
    rows["prev_day_mean"] = rows["prev_day_total"] / 24.0

    # missing-hour report ------------------------------------------------
    expected_buckets = (10 * 28 * 24)
    missing_rows = rows["energy_kwh"].isna().sum()
    print("MISSING-HOUR CHECK (one row per region and CAT hour expected)")
    print(f"  expected region-hour rows  {expected_buckets:,}")
    print(f"  present rows               {len(rows):,}")
    print(f"  absent hour rows           {int(missing_rows):,} "
          "(targets with no stored aggregate)")
    absent_targets = rows[rows["energy_kwh"].isna()]
    if not absent_targets.empty:
        print("  absent bucket examples:")
        print(absent_targets.head(5).to_string(index=False))
    print("")

    # splits -------------------------------------------------------------
    rows["split"] = "train"
    rows.loc[(rows["hour_start"] >= VAL_START)
             & (rows["hour_start"] < TEST_START), "split"] = "validation"
    rows.loc[(rows["hour_start"] >= TEST_START)
             & (rows["hour_start"] < TEST_END), "split"] = "test"
    train = rows[rows["split"] == "train"].copy()
    train = train[train["hour_start"] >= TRAIN_START]

    print("SPLIT BY TARGET TIMESTAMP")
    print(f"  {'split':<12}{'first hour':<24}{'last hour':<24}{'rows':>8}")
    for split, group in rows.groupby("split"):
        print(f"  {split:<12}{cat_text(group['hour_start'].min()):<24}"
              f"{cat_text(group['hour_start'].max()):<24}{len(group):>8}")

    # lookback exclusions on the training split --------------------------
    EARLIEST_USABLE = pd.Timestamp("2026-09-03T00:00:00+02:00")
    before_lookback_rows = train[train["hour_start"] < EARLIEST_USABLE]
    usable_train = train[train["hour_start"] >= EARLIEST_USABLE].copy()
    usable_train = usable_train.dropna(subset=["lag1d", "lag2d"])

    print("")
    print("FEATURE TABLE")
    print("  feature       lag/window (h)  earliest usable target")
    print("  lag1d         24              2026-09-02 00:00 CAT")
    print("  lag2d         48              2026-09-03 00:00 CAT")
    print("  prev_day_mean window 24h      2026-09-02 00:00 CAT")
    print("  hour, day_of_week, is_weekend, day_index (calendar, no lag)")
    print("  region        one-hot (categorical)")
    print("")
    print("LOOKBACK EXCLUSION (training split)")
    print(f"  training rows before lookback   {len(before_lookback_rows):,}")
    print(f"  rows with missing lag values    "
          f"{int(train[train['hour_start'] >= EARLIEST_USABLE]['lag1d'].isna().sum() + train[train['hour_start'] >= EARLIEST_USABLE]['lag2d'].isna().sum()):,}")
    print(f"  retained usable training rows   {len(usable_train):,}")

    # persist -------------------------------------------------------------
    data_dir = Path(PROJECT_ROOT) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    rows.to_csv(data_dir / "forecast_dataset.csv", index=False)
    rows.to_parquet(data_dir / "forecast_dataset.parquet")
    print(f"Saved data/forecast_dataset.csv and .parquet")
    print(f"Completed {cat_text()} CAT")
    print(f"Duration {(cat_now() - started).total_seconds():.3f} s")


if __name__ == "__main__":
    run_with_log("forecast_dataset", main)