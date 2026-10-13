"""Section 1.3 step 1: publish the pilot stream to MQTT.

PURPOSE
    Take the first 2,000 reading dictionaries from the unchanged generator's
    iter_readings(), convert each to JSON and publish exactly one MQTT message
    per dictionary to the topic energy/meters/{meter_id}, at QoS 1 with the
    retained flag off.

    The pilot replays historical readings: iter_readings() yields the whole
    September series in event_time order, so 2,000 messages leave in fractions
    of a second instead of one every 15 minutes.

INPUTS
    - smart_meter_simulator.iter_readings()   (unchanged supplied generator)
    - config.py                               (broker host, port)

OUTPUTS
    - 2,000 MQTT messages published
    - dictionaries taken and broker acknowledgements, printed and written to
      logs/pilot_counts.json so the subscriber can build the single report
      table required by Section 1.3.3

HOW TO RUN
    Start the subscriber first (Section 1.3.2), then:

        python ingestion\\pilot_publish.py
"""

import json
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

import smart_meter_simulator  # noqa: E402 - the supplied file, imported unchanged

from common.cat_time import cat_text  # noqa: E402
from common.db import load_config, log_directory  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402

# Section 1.3.1 fixes the size of the pilot at 2,000 dictionaries.
PILOT_SIZE = 2000
TOPIC_PREFIX = "energy/meters"

# QoS 1 (at least once) with retain=False, both required by Section 1.3.1.
QOS = 1
RETAIN = False


def take_readings(how_many: int) -> list[dict]:
    """Return the first `how_many` dictionaries from a fresh iterator.

    WHY A FRESH ITERATOR
        iter_readings() restarts the dataset on every call, so this program
        always publishes the same first 2,000 readings as any other run. The
        full historical capture in Section 2.1 opens its own iterator.
    """
    readings: list[dict] = []
    for reading in smart_meter_simulator.iter_readings():
        readings.append(reading)
        if len(readings) >= how_many:
            break
    return readings


def publish(readings: list[dict]) -> tuple[int, float]:
    """Publish every reading and return (acknowledged_count, elapsed_seconds).

    HOW ACKNOWLEDGEMENTS ARE COUNTED
        QoS 1 makes the broker send a PUBACK for every message. paho-mqtt calls
        the on_publish callback when that PUBACK arrives, so the callback counts
        acknowledgements rather than assuming that "publish returned" means
        "broker received". That distinction is exactly what Section 1.3.3 asks
        us to measure.
    """
    settings = load_config()

    acknowledged = {"count": 0}
    connected = {"flag": False}

    # paho-mqtt 2.x requires the callback API version to be stated explicitly.
    # Passing VERSION2 keeps the newer signatures for on_connect/on_publish.
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="pilot_publisher",
        clean_session=True,
    )

    def on_connect(client, userdata, flags, reason_code, properties=None):
        connected["flag"] = reason_code.is_failure is False

    def on_publish(client, userdata, mid, reason_code=None, properties=None):
        acknowledged["count"] += 1

    client.on_connect = on_connect
    client.on_publish = on_publish

    client.connect(settings["MQTT_HOST"], int(settings["MQTT_PORT"]),
                   keepalive=int(settings.get("MQTT_KEEPALIVE", 60)))
    client.loop_start()

    # Wait for the CONNACK before publishing, otherwise the first messages can
    # be queued silently and the acknowledgement count becomes meaningless.
    deadline = time.time() + 10
    while not connected["flag"] and time.time() < deadline:
        time.sleep(0.05)
    if not connected["flag"]:
        client.loop_stop()
        client.disconnect()
        raise SystemExit("Could not connect to the MQTT broker. Is EMQX running?")

    started = time.monotonic()
    for reading in readings:
        topic = f"{TOPIC_PREFIX}/{reading['meter_id']}"
        payload = json.dumps(reading)
        client.publish(topic, payload, qos=QOS, retain=RETAIN)

    # Drain the acknowledgement queue before stopping the network loop.
    deadline = time.time() + 60
    while acknowledged["count"] < len(readings) and time.time() < deadline:
        time.sleep(0.05)
    elapsed = time.monotonic() - started

    client.loop_stop()
    client.disconnect()
    return acknowledged["count"], elapsed


def main() -> None:
    print("=" * 78)
    print("Section 1.3  Pilot publisher")
    print(f"Started {cat_text()} CAT")
    print("=" * 78)
    print("")
    print(f"  Topic pattern      {TOPIC_PREFIX}/{{meter_id}}")
    print(f"  QoS                {QOS}")
    print(f"  Retained messages  {RETAIN}")
    print("")

    print(f"Taking the first {PILOT_SIZE} dictionaries from iter_readings()")
    readings = take_readings(PILOT_SIZE)
    dictionaries_taken = len(readings)
    print(f"  dictionaries taken {dictionaries_taken}")
    if dictionaries_taken != PILOT_SIZE:
        raise SystemExit(
            f"Generator returned only {dictionaries_taken} readings; "
            f"{PILOT_SIZE} were required. Stopping before publishing."
        )

    distinct_meters = len({r["meter_id"] for r in readings})
    first_event = readings[0]["event_time"]
    last_event = readings[-1]["event_time"]
    print(f"  distinct meters     {distinct_meters}")
    print(f"  first event_time    {first_event}")
    print(f"  last  event_time    {last_event}")
    print("")

    print(f"Publishing {dictionaries_taken} JSON messages to the broker")
    acknowledged, elapsed = publish(readings)
    print(f"  published           {dictionaries_taken}")
    print(f"  acknowledged (PUBACK) {acknowledged}")
    print(f"  elapsed seconds     {elapsed:.3f}")
    print("")

    print("=" * 78)
    print("PUBLISHER COMPLETION")
    print("=" * 78)
    if acknowledged == dictionaries_taken:
        print("  PASS: every published message was acknowledged by the broker.")
    else:
        print(
            f"  DIFFERENCE: {dictionaries_taken - acknowledged} message(s) "
            "were not acknowledged. Check the EMQX log."
        )

    # Hand the counts to the summary builder so Section 1.3.3 can print one
    # table containing all four counts.
    counts_path = log_directory() / "pilot_counts.json"
    payload = {
        "dictionaries_taken": dictionaries_taken,
        "broker_acknowledged": acknowledged,
        "publisher_elapsed_seconds": round(elapsed, 3),
        "published_at": cat_text(),
    }
    counts_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("")
    print(f"  Counts written to {counts_path}")


if __name__ == "__main__":
    run_with_log("pilot_publish", main)
