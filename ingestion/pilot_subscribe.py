"""Section 1.3 step 2: subscribe to the pilot stream and write it to energy_live.

PURPOSE
    Subscribe to energy/meters/# at QoS 1, parse each JSON payload and insert
    its eight fields as one row in energy_live. The subscriber is started
    BEFORE the publisher (Section 1.3.2) so that no message can be published
    before a consumer exists.

    Deliberate duplicates from the generator are counted as separate messages
    and separate rows, exactly as Section 1.3.3 requires. Nothing is
    de-duplicated here: energy_live is the raw pilot landing table.

INPUTS
    - MQTT topics energy/meters/# from the pilot publisher
    - config.py for the broker and database settings

OUTPUTS
    - one energy_live row per received message, committed at the end
    - received / parsed / inserted counts, printed and merged into
      logs/pilot_counts.json for the single report table of Section 1.3.3

HOW TO RUN
    Window 1 (start first):

        python ingestion\\pilot_subscribe.py

    Window 2 (start second):

        python ingestion\\pilot_publish.py

    The subscriber exits by itself once it has stored the expected number of
    rows, or after --timeout seconds.
"""

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from common.cat_time import cat_text  # noqa: E402
from common.db import connect, load_config, log_directory  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402

EXPECTED_ROWS = 2000
TOPIC_FILTER = "energy/meters/#"
QOS = 1

# Eight columns, in the order used by the INSERT below. The reading
# dictionaries carry exactly these keys.
FIELDS = [
    "meter_id",
    "event_time",
    "received_time",
    "power_kw",
    "voltage_v",
    "current_a",
    "frequency_hz",
    "energy_kwh",
]

INSERT_STATEMENT = """
    INSERT INTO energy_live
        (meter_id, event_time, received_time, power_kw, voltage_v,
         current_a, frequency_hz, energy_kwh)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""

# Rows are buffered and written in batches. A commit per message would make the
# subscriber the bottleneck and would distort the pilot's timing; one transaction
# per 500 rows commits well before the final count is taken.
BATCH_SIZE = 500


def run_subscriber(expected: int, timeout: float) -> None:
    """Subscribe, insert, then report the four counts for Section 1.3.3.

    WHY A QUEUE AND A SEPARATE WRITER THREAD
        paho-mqtt runs every callback on ONE network thread. If that thread
        blocks inside a database insert, it stops reading the socket, the TCP
        receive window closes, the broker's in-flight window for this client
        fills up and EMQX starts dropping QoS 1 deliveries. Measured on this
        machine: inserting inside the callback stored only 1,531 of 2,000
        messages, while the same 2,000 inserts take 1.1 seconds on their own.
        So the database was never the bottleneck; blocking the network thread
        was. The callback now parses and enqueues, and a writer thread owns the
        connection and the transaction.
    """
    settings = load_config()

    received = {"count": 0}
    parse_errors = {"count": 0, "examples": []}
    insert_errors = {"count": 0, "examples": []}
    connected = {"flag": False}
    finished = {"flag": False}

    # A plain list used as a queue, guarded by a lock. Messages are tiny and
    # the critical section is a pointer append, so this costs microseconds.
    pending: list[tuple] = []
    pending_lock = threading.Lock()
    writer_done = threading.Event()
    inserted_total = {"count": 0}

    def writer() -> None:
        """Own the database connection: drain the queue in batches and commit."""
        connection = connect()
        cursor = connection.cursor()
        try:
            while True:
                with pending_lock:
                    batch = pending[:BATCH_SIZE]
                    del pending[:BATCH_SIZE]

                if batch:
                    try:
                        cursor.executemany(INSERT_STATEMENT, batch)
                        inserted_total["count"] += len(batch)
                    except Exception as error:  # noqa: BLE001 - reported
                        insert_errors["count"] += len(batch)
                        if len(insert_errors["examples"]) < 5:
                            insert_errors["examples"].append(str(error))
                    # Commit per batch so the final row count is visible
                    # immediately after the subscriber reports it.
                    connection.commit()
                    if inserted_total["count"] % (BATCH_SIZE * 4) == 0:
                        print(f"  stored {inserted_total['count']} rows ...",
                              flush=True)
                    continue

                if writer_done.is_set():
                    # Drain once more in case a row arrived with the flag.
                    with pending_lock:
                        remaining = list(pending)
                        pending.clear()
                    if remaining:
                        cursor.executemany(INSERT_STATEMENT, remaining)
                        inserted_total["count"] += len(remaining)
                        connection.commit()
                    break
                time.sleep(0.01)
        finally:
            cursor.close()
            connection.close()

    def on_connect(client, userdata, flags, reason_code, properties=None):
        connected["flag"] = reason_code.is_failure is False
        if connected["flag"]:
            # QoS 1 subscription, as Section 1.3.2 requires.
            client.subscribe(TOPIC_FILTER, qos=QOS)

    def on_message(client, userdata, message):
        # Fast path only: parse and enqueue. No database work here.
        received["count"] += 1
        try:
            reading = json.loads(message.payload.decode("utf-8"))
            row = tuple(reading[field] for field in FIELDS)
        except Exception as error:  # noqa: BLE001 - reported, not hidden
            parse_errors["count"] += 1
            if len(parse_errors["examples"]) < 5:
                parse_errors["examples"].append(str(error))
            return
        with pending_lock:
            pending.append(row)

        if received["count"] >= expected:
            finished["flag"] = True

    writer_thread = threading.Thread(target=writer, name="energy_live_writer",
                                     daemon=True)
    writer_thread.start()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="pilot_subscriber",
        clean_session=True,
    )
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to {settings['MQTT_HOST']}:{settings['MQTT_PORT']} "
          f"and subscribing to {TOPIC_FILTER} at QoS {QOS}")
    client.connect(settings["MQTT_HOST"], int(settings["MQTT_PORT"]),
                   keepalive=int(settings.get("MQTT_KEEPALIVE", 60)))
    client.loop_start()

    started = time.monotonic()
    deadline = started + timeout
    while time.monotonic() < deadline:
        if finished["flag"]:
            break
        time.sleep(0.1)

    # Give in-flight QoS 1 deliveries a moment to land before closing.
    if received["count"] >= expected:
        grace = time.monotonic() + 5
        while time.monotonic() < grace and received["count"] < expected:
            time.sleep(0.1)

    client.loop_stop()
    client.disconnect()

    # Hand the queue to the writer and wait until every row is committed, so
    # the reported row count can never lag behind the received count.
    writer_done.set()
    writer_thread.join(timeout=120)
    elapsed = time.monotonic() - started

    check = connect()
    with check.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM energy_live")
        stored_rows = cursor.fetchone()[0]
        cursor.execute("SELECT min(event_time), max(event_time) FROM energy_live")
        first_event, last_event = cursor.fetchone()
    check.close()

    print("")
    print("=" * 78)
    print("SUBSCRIBER FINISHED")
    print("=" * 78)
    print(f"  finished at                 {cat_text()} CAT")
    print(f"  messages received           {received['count']}")
    print(f"  JSON parsing errors         {parse_errors['count']}")
    for example in parse_errors["examples"]:
        print(f"      {example}")
    print(f"  rows inserted (this run)    {inserted_total['count']}")
    print(f"  insert errors               {insert_errors['count']}")
    for example in insert_errors["examples"]:
        print(f"      {example}")
    print(f"  rows committed to energy_live {stored_rows}")
    print(f"  earliest event_time         {first_event}")
    print(f"  latest   event_time         {last_event}")
    print(f"  elapsed seconds             {elapsed:.3f}")
    print("")

    if stored_rows == expected:
        print(f"  PASS: energy_live holds exactly {expected} rows.")
    else:
        print(
            f"  DIFFERENCE: expected {expected} rows, found {stored_rows}. "
            "Compare the received, parsing and insert counts above."
        )

    # Merge with whatever the publisher recorded, so one file holds all counts.
    counts_path = log_directory() / "pilot_counts.json"
    counts: dict = {}
    if counts_path.exists():
        counts = json.loads(counts_path.read_text(encoding="utf-8"))
    counts.update(
        {
            "subscriber_received": received["count"],
            "subscriber_parse_errors": parse_errors["count"],
            "subscriber_inserted": inserted_total["count"],
            "energy_live_rows": stored_rows,
            "subscriber_elapsed_seconds": round(elapsed, 3),
            "subscriber_finished_at": cat_text(),
        }
    )
    counts_path.write_text(json.dumps(counts, indent=2), encoding="utf-8")
    print(f"  Counts written to {counts_path}")

    # Section 1.3.3 asks for all four counts in ONE table. The publisher writes
    # its two counts to pilot_counts.json, so the table can be built here.
    print("")
    print("=" * 78)
    print("SECTION 1.3.3  FOUR COUNTS")
    print("=" * 78)
    header = f"  {'Stage':<40}{'Count':>10}  {'Expected':>10}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    rows = [
        ("1  dictionaries taken from generator",
         counts.get("dictionaries_taken"), expected),
        ("2  messages acknowledged by broker (PUBACK)",
         counts.get("broker_acknowledged"), expected),
        ("3  messages received by subscriber",
         counts.get("subscriber_received"), expected),
        ("4  rows committed in energy_live",
         counts.get("energy_live_rows"), expected),
    ]
    all_match = True
    for label, value, target in rows:
        value_text = "n/a" if value is None else str(value)
        flag = "" if value == target else "   <-- differs"
        if value != target:
            all_match = False
        print(f"  {label:<40}{value_text:>10}  {target:>10}{flag}")
    print("")
    if all_match:
        print("  PASS: all four counts equal the 2,000-message target.")
    else:
        print("  One or more counts differ from 2,000; see the log above.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Subscribe to the pilot MQTT stream and load it into energy_live."
    )
    parser.add_argument("--expect", type=int, default=EXPECTED_ROWS,
                        help="rows expected from the publisher (default 2000)")
    parser.add_argument("--timeout", type=float, default=300,
                        help="seconds to wait before giving up (default 300)")
    arguments = parser.parse_args()

    print("=" * 78)
    print("Section 1.3  Pilot subscriber")
    print(f"Started {cat_text()} CAT")
    print("=" * 78)
    print("")
    print("  energy_live is truncated first so each run starts empty,")
    print("  which is what Section 1.3.2 asks for.")
    print("")

    connection = connect()
    with connection.cursor() as cursor:
        cursor.execute("TRUNCATE energy_live")
    connection.commit()
    connection.close()

    run_subscriber(arguments.expect, arguments.timeout)


if __name__ == "__main__":
    run_with_log("pilot_subscribe", main)
