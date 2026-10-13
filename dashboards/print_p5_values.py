"""Print the exact P5 completeness values for both dashboard modes (FIX 1).

Runs the same P5 SQL the Raw and Aggregate dashboards execute and prints, per
region: registered meters, observed readings, planned readings and completeness
to six decimals, so the two modes can be compared directly.

    python dashboards\\print_p5_values.py
"""

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "dashboards"))

from common.cat_time import cat_text  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402
from dashboard_data import run_agg, run_raw  # noqa: E402

START = datetime.fromisoformat("2026-09-22T00:00:00+02:00")
END = datetime.fromisoformat("2026-09-29T00:00:00+02:00")


def dump(mode, rows):
    print(f"  --- {mode} mode ---")
    print(f"  {'region':<10}{'registered':>11}{'observed':>11}{'planned':>10}"
          f"{'completeness':>16}")
    print("  " + "-" * 56)
    for row in rows:
        print(f"  {row['region']:<10}{row['registered']:>11}{row['observed']:>11}"
              f"{row['planned']:>10}{row['completeness']:>16.6f}")
    print("")


def main():
    print("=" * 78)
    print(f"P5 completeness values  {cat_text()} CAT")
    print(f"Range [{START} .. {END}) exclusive  (7 days, end exclusive)")
    print("=" * 78)
    print("")

    raw = run_raw(START, END, 1000000000)["P5"].rows
    agg = run_agg(START, END, 1000000000)["P5"].rows
    dump("Raw", raw)
    dump("Aggregate", agg)

    by_region = {r["region"]: r for r in agg}
    print("  Agreement check (Raw vs Aggregate):")
    worst = 0.0
    for row in raw:
        other = by_region[row["region"]]
        diff = abs(row["completeness"] - other["completeness"])
        worst = max(worst, diff)
        print(f"    {row['region']:<10} observed {row['observed']:>8} vs "
              f"{other['observed']:>8}   completeness "
              f"{row['completeness']:.6f} vs {other['completeness']:.6f}")
    print("")
    print(f"  Max completeness difference {worst:.9f} percentage points")
    print(f"  Planned for 400 meters x 7 days x 96 = "
          f"{400 * 7 * 96} per region (shown above)")


if __name__ == "__main__":
    run_with_log("print_p5_values", main)
