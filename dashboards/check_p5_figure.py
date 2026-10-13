"""Confirm the P5 figure carries value labels and an honest y-axis (FIX 1).

Builds the P5 figure exactly as the dashboards do (app.build), for both modes,
and prints the bar text labels, the y-axis range and the y-axis title.

    python dashboards\\check_p5_figure.py
"""

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "dashboards"))

import app  # noqa: E402

START = datetime.fromisoformat("2026-09-22T00:00:00+02:00")
END = datetime.fromisoformat("2026-09-29T00:00:00+02:00")


def main():
    for mode in ("Raw", "Aggregate"):
        figures, timings = app.build(mode, START, END, 1000000000)
        trace = figures["P5"].data[0]
        layout = figures["P5"].layout
        print(f"MODE {mode}")
        print(f"  P5 bar text labels : {list(trace.text)}")
        print(f"  P5 y-axis range    : {layout.yaxis.range}")
        print(f"  P5 y-axis title    : {layout.yaxis.title.text}")
        print(f"  P5 query time      : {timings['P5']:.3f} ms")
        print("")


if __name__ == "__main__":
    main()
