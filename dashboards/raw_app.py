"""Run the Raw dashboard (Section 7.1) on http://127.0.0.1:8050.

Every measurement query reads energy_readings directly and joins meters where a
region label is needed. Panel SQL lives in sql/dashboards/raw/*.sql.

    python dashboards\\raw_app.py
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
    port = int(os.environ.get("RAW_PORT", "8050"))
    print(f"Starting Raw dashboard {cat_text()} CAT on port {port}")
    create_app("Raw").run(debug=False, host="127.0.0.1", port=port)
