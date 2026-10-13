"""Section 3.2 step 5: capture one EXPLAIN ANALYZE plan per configuration.

PURPOSE
    Section 3.2.5 requires one execution plan with actual timing and buffer
    statistics per configuration (energy_readings, energy_readings_3h,
    energy_readings_week). This script runs Q1 (the per-hour average on 21
    September, which returns only 24 rows) with EXPLAIN (ANALYZE, BUFFERS,
    VERBOSE, COSTS) on each of the three tables and writes the plans to
    logs/explain_chunk_configs.txt for the report.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.db import connect  # noqa: E402

PLAN_SQL = """
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, COSTS)
SELECT time_bucket(INTERVAL '1 hour', event_time) AS hour_start,
       avg(power_kw) AS average_power_kw
FROM {table}
WHERE event_time >= TIMESTAMPTZ '2026-09-21 00:00:00+02'
  AND event_time <  TIMESTAMPTZ '2026-09-22 00:00:00+02'
GROUP BY hour_start
ORDER BY hour_start
"""

TABLES = ["energy_readings", "energy_readings_3h", "energy_readings_week"]


def main() -> None:
    blocks: list[str] = []
    for table in TABLES:
        connection = connect(application_name="smart-energy-grid")
        try:
            with connection.cursor() as cursor:
                cursor.execute(PLAN_SQL.format(table=table))
                lines = [row[0] for row in cursor.fetchall()]
        finally:
            connection.close()
        blocks.append(f"===== EXPLAIN ANALYZE Q1 on {table} =====")
        blocks.extend(lines)
        blocks.append("")

    text = "\n".join(blocks)
    target = PROJECT_ROOT / "logs" / "explain_chunk_configs.txt"
    target.write_text(text, encoding="utf-8")
    print(text)
    print(f"Plans written to {target}")


if __name__ == "__main__":
    main()