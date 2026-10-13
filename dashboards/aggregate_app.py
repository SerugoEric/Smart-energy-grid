"""Run the Aggregate dashboard (Section 7.2) on http://127.0.0.1:8051.

Every measurement query reads the Section 6.1 continuous aggregates; meters is
queried only for labels and registered counts. Panel SQL lives in
sql/dashboards/aggregate/*.sql.

    python dashboards\\aggregate_app.py
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import create_app  # noqa: E402
from common.cat_time import cat_text  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("AGGREGATE_PORT", "8051"))
    print(f"Starting Aggregate dashboard {cat_text()} CAT on port {port}")
    create_app("Aggregate").run(debug=False, host="127.0.0.1", port=port)
