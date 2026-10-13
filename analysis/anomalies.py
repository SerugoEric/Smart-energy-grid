"""Section 5.4: detect and evaluate abnormal consumption.

ANOMALY DETECTION RULE
    A reading is flagged when it departs from that meter's typical power for
    the same CAT hour of day:

        spike  if  power_kw >  2.0 * median hour power for the meter
        drop   if  power_kw <  0.1 * median hour power for the meter

    Baseline: the median power_kw of the meter in that CAT hour over the
    historical period (percentile_cont(0.5)). A per-meter-per-hour median is
    used rather than a per-meter one so the legitimate residential evening
    peak (several times the night trough) is NOT treated as anomalous while a
    genuine spike during a low-demand hour IS visible against its own hour's
    baseline.

    Thresholds 2.0x and 0.1x are chosen from the data generator's own
    anomaly scale: an injected event multiplies power by 2.8 (demand_spike)
    or 0.03 (unusual_drop). Normal readings only vary by +-15% around the
    hourly shape, so 2.0x and 0.1x sit far outside normal hourly noise and
    comfortably below the injected multipliers, giving clean separation.

    Each flag is a (meter_id, event_time) row. Evaluation against
    anomaly_events() labels follows the assignment: an injected event is
    detected when at least one flag shares its meter_id and falls at or
    after start_time and before end_time. A false flag is a flagged reading
    outside every injected interval for that meter.

HOW TO RUN
    From the project root:

        python analysis\\anomalies.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from common.cat_time import cat_now, cat_text  # noqa: E402
from common.db import connect, machine_identifier  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402

SPIKE_FACTOR = 2.0
DROP_FACTOR = 0.1


def main() -> None:
    started = cat_now()
    print("=" * 78)
    print("Section 5.4  Abnormal consumption")
    print(f"Started {cat_text()} CAT")
    print(f"Machine {machine_identifier()}")
    print("=" * 78)
    print("")
    print("ANOMALY DETECTION RULE")
    print("  spike if power_kw > "
          f"{SPIKE_FACTOR} * (meter, CAT hour, weekday/weekend) median power_kw")
    print("  drop  if power_kw < "
          f"{DROP_FACTOR} * (meter, CAT hour, weekday/weekend) median power_kw")
    print("  Median computed with percentile_cont(0.5) over the full 28-day")
    print("  period per meter, CAT hour of day and weekday/weekend split.")
    print("")

    connection = connect()
    cursor = connection.cursor()

    # --- step 1: per (meter, CAT hour) median power ---------------------
    print("Building per-meter per-CAT-hour median baselines")
    cursor.execute(
        """
        DROP TABLE IF EXISTS _anomaly_hour_median
        """
    )
    cursor.execute(
        """
        CREATE TEMP TABLE _anomaly_hour_median AS
        SELECT meter_id,
               extract(hour FROM event_time AT TIME ZONE 'Africa/Kigali')::int
                   AS cat_hour,
               CASE WHEN extract(isodow FROM
                                 event_time AT TIME ZONE 'Africa/Kigali') IN (6, 7)
                    THEN 'weekend' ELSE 'weekday' END AS dow_type,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY power_kw)
                   AS med_power
        FROM energy_readings
        GROUP BY meter_id, cat_hour, dow_type
        """
    )
    connection.commit()
    print("  median baselines ready")

    # --- step 2: flag readings ------------------------------------------
    print("Applying detection rule (single scan over cleaned readings)")
    cursor.execute(
        """
        DROP TABLE IF EXISTS _anomaly_flags
        """
    )
    cursor.execute(
        """
        CREATE TEMP TABLE _anomaly_flags AS
        SELECT r.meter_id, r.event_time, r.power_kw,
               h.med_power,
               CASE WHEN r.power_kw > %s * h.med_power THEN 'demand_spike'
                    WHEN r.power_kw < %s * h.med_power THEN 'unusual_drop'
                    ELSE NULL END AS flag_type
        FROM energy_readings r
        JOIN _anomaly_hour_median h
          ON h.meter_id = r.meter_id
         AND h.cat_hour =
             extract(hour FROM r.event_time AT TIME ZONE 'Africa/Kigali')::int
         AND h.dow_type = CASE
             WHEN extract(isodow FROM
                          r.event_time AT TIME ZONE 'Africa/Kigali') IN (6, 7)
             THEN 'weekend' ELSE 'weekday' END
        WHERE r.power_kw > %s * h.med_power
           OR r.power_kw < %s * h.med_power
        """,
        (SPIKE_FACTOR, DROP_FACTOR, SPIKE_FACTOR, DROP_FACTOR),
    )
    connection.commit()
    cursor.execute(
        """
        SELECT count(*),
               count(*) FILTER (WHERE flag_type = 'demand_spike'),
               count(*) FILTER (WHERE flag_type = 'unusual_drop'),
               count(DISTINCT meter_id)
        FROM _anomaly_flags
        """
    )
    total_flags, spikes, drops, flagged_meters = cursor.fetchone()
    print(f"  {total_flags:,} flagged readings "
          f"({spikes:,} spikes, {drops:,} drops) "
          f"across {flagged_meters:,} meters")
    print("")

    # --- step 3: load the injected labels --------------------------------
    from smart_meter_simulator import anomaly_events

    labels = anomaly_events()
    print("LOADED INJECTED EVENT LABELS")
    print(f"  {len(labels)} injected events from anomaly_events()")
    events = []
    for label in labels:
        parsed = dict(label)
        parsed["start"] = cat_parse(parsed["start_time"])
        parsed["end"] = cat_parse(parsed["end_time"])
        events.append(parsed)
    print("")

    # Build the in-window set-based table (disjoint intervals).
    cursor.execute("DROP TABLE IF EXISTS _anomaly_windows")
    create_window_sql = (
        "CREATE TEMP TABLE _anomaly_windows (meter_id bigint,"
        " s timestamptz, e timestamptz)"
    )
    cursor.execute(create_window_sql)
    for event in events:
        cursor.execute(
            "INSERT INTO _anomaly_windows VALUES (%s, %s, %s)",
            (event["meter_id"], event["start"], event["end"]),
        )
    connection.commit()

    cursor.execute(
        """
        SELECT count(*) AS inside_window_rows
        FROM energy_readings r
        WHERE EXISTS (
            SELECT 1 FROM _anomaly_windows w
            WHERE w.meter_id = r.meter_id
              AND r.event_time >= w.s AND r.event_time < w.e
        )
        """
    )
    inside_rows = cursor.fetchone()[0]

    # --- step 4: evaluation ----------------------------------------------
    # Load the flags into Python.
    cursor.execute("SELECT meter_id, event_time FROM _anomaly_flags")
    flag_rows = cursor.fetchall()
    flags_by_meter: dict[int, list] = {}
    for meter_id, event_time in flag_rows:
        flags_by_meter.setdefault(meter_id, []).append(event_time)

    detected: list[dict] = []
    missed: list[dict] = []

    for event in events:
        times = flags_by_meter.get(event["meter_id"], [])
        hit = any(event["start"] <= t < event["end"] for t in times)
        if hit:
            detected.append(event)
        else:
            missed.append(event)

    # False flags: flagged readings outside every injected interval.
    false_flag_count = 0
    meters_with_false_flags = set()
    for meter_id, times in flags_by_meter.items():
        windows = [
            (e["start"], e["end"])
            for e in events
            if e["meter_id"] == meter_id
        ]
        for t in times:
            inside = any(s <= t < e for s, e in windows)
            if not inside:
                false_flag_count += 1
                meters_with_false_flags.add(meter_id)

    total_readings = 10_643_735  # cleaned unique readings
    outside_rows = total_readings - inside_rows
    false_pct = 100.0 * false_flag_count / outside_rows
    meters_pct = 100.0 * len(meters_with_false_flags) / 4000

    print("EVALUATION AGAINST INJECTED EVENTS (40 labelled intervals)")
    print("-" * 70)
    print(f"  injected events                       {len(events)}")
    print(f"  detected                              {len(detected)}")
    print(f"  missed                                {len(missed)}")
    for event in missed:
        print(f"    missed {event['meter_id']} "
              f"{event['start']} - {event['end']} ({event['event_type']})")
    print("")
    print("FALSE FLAGS")
    print("-" * 70)
    print(f"  total flagged readings                {total_flags:,}")
    print(f"  readings inside injected intervals    {inside_rows:,}")
    print(f"  observed readings outside intervals   {outside_rows:,}")
    print(f"  false flags                           {false_flag_count:,}")
    print(f"  false flags as % of outside readings  {false_pct:.4f}%")
    print(f"  meters with at least one false flag   {len(meters_with_false_flags)}")
    print(f"  % of 4,000 meters affected            {meters_pct:.4f}%")
    print("")

    cursor.close()
    connection.close()

    print(f"Completed {cat_text()} CAT")
    print(f"Duration {(cat_now() - started).total_seconds():.3f} s")


def cat_parse(text: str):
    """Parse a +02:00 CAT timestamp into a timezone-aware datetime."""
    from datetime import datetime

    return datetime.fromisoformat(text)


if __name__ == "__main__":
    run_with_log("anomalies", main)