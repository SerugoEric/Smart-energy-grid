"""Section 1.2 step 4: load the 4,000 meter metadata rows into the meters table.

PURPOSE
    Section 1.2.4 requires a Python program that imports the unchanged supplied
    generator, calls meter_metadata(), and inserts every returned dictionary as
    one row in meters. It then requires verification that meters contains 4,000
    rows. This program is that loader.

    Nothing about the 4,000 meters is written by hand in this file. The rows come
    from meter_metadata() and nowhere else, so the meters table cannot drift from
    what the generator defines.

INPUTS
    - smart_meter_simulator.meter_metadata()  (the unchanged supplied file)
    - the meters table created by sql/01_schema.sql
    - config.py for the database connection settings

OUTPUTS
    - 4,000 rows in meters
    - a console report that doubles as the Section 1.2 screenshot
    - the same report in logs/meters_load_<timestamp>.txt

HOW TO RUN
    From the project root:

        python ingestion\\load_meters.py

    Verify afterwards, in a second window, with:

        docker exec -it timescaledb psql -U auca -d smart_energy_grid -c "SELECT count(*) FROM meters;"

    The result must be 4000.

WHY A SEED FLAG EXISTS
    meters has a primary key on meter_id, so running this program twice raises a
    duplicate key error on the second run. The default behaviour is therefore to
    refuse to run when the table is not empty, rather than to half-succeed.
    --reset truncates first, which is the safe way to reload from scratch.
"""

import argparse
import sys

# WHY WE ADD THE PROJECT ROOT TO sys.path
#     Python puts the SCRIPT'S folder on the module search path, not the folder you
#     happen to be working in. This file lives in ingestion/, while
#     smart_meter_simulator.py and the common/ package live in the project root one
#     level up. So without this line, running "python ingestion\load_meters.py" from
#     the root would still fail with ModuleNotFoundError.
#
#     rsplit is used instead of splitting on "\\" directly, so the script also works
#     when it is run on a system whose path separator is not a backslash.
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

import smart_meter_simulator  # noqa: E402 - the supplied file, imported unchanged

from common.cat_time import cat_text, cat_timer  # noqa: E402
from common.db import connect  # noqa: E402
from common.logging_utils import run_with_log  # noqa: E402

# How many rows to send per INSERT. 4,000 rows would work as one statement, but
# batching is the habit the assignment asks for, and the same helper will send
# 50,000-row batches in Section 2.1.
BATCH_SIZE = 1000


def read_expected_meter_count() -> int:
    """Return the meter count the generator declares in dataset_info().

    WHY NOT HARD-CODE 4000
        The assignment states 4,000, and dataset_info() states it too. Reading it
        from the generator means this program checks itself against the same
        source of truth the data comes from, so if the two ever disagreed we would
        find out here instead of after a failed load.
    """
    return int(smart_meter_simulator.dataset_info()["meters"])


def load_meter_rows(rows: list[dict], reset: bool) -> int:
    """Insert the meter dictionaries into meters and return the row count inserted.

    WHY ONE execute_batch CALL RATHER THAN A LOOP
        One INSERT statement carrying many value tuples is sent as a single round
        trip to PostgreSQL. A Python loop would send one round trip per row, which
        for 4,000 rows is slow enough to be noticeable over a network connection.

    WHY THE EXPLICIT COLUMN LIST
        execute_batch builds "INSERT INTO meters VALUES %s" with one placeholder
        per value. Naming the columns means a column added to the table later
        cannot silently shift every value into the wrong field.
    """
    inserted_total = 0

    with cat_timer(f"insert {len(rows)} rows into meters"):
        connection = connect()
        try:
            with connection:
                with connection.cursor() as cursor:
                    if reset:
                        # TRUNCATE is faster than DELETE and resets the table
                        # completely. Without CASCADE it will refuse while other
                        # tables reference meters, which is the safe behaviour.
                        cursor.execute("TRUNCATE meters")
                        print("  meters truncated (--reset was given)")

                    insert_statement = """
                        INSERT INTO meters
                            (meter_id, region, customer_type, base_power_kw, power_factor)
                        VALUES (%s, %s, %s, %s, %s)
                    """

                    for start in range(0, len(rows), BATCH_SIZE):
                        batch = rows[start:start + BATCH_SIZE]

                        # Turn each dictionary into a tuple in the column order the
                        # INSERT statement above expects. Doing the ordering here,
                        # once, keeps the SQL simple and makes the mapping obvious.
                        values = [
                            (
                                meter["meter_id"],
                                meter["region"],
                                meter["customer_type"],
                                meter["base_power_kw"],
                                meter["power_factor"],
                            )
                            for meter in batch
                        ]

                        cursor.executemany(insert_statement, values)
                        inserted_total += len(values)

                        print(f"  inserted {inserted_total} of {len(rows)} meters")

            # The psycopg2 connection context manager commits on a clean exit and
            # rolls back on an exception, so nothing is left half-written.
        finally:
            connection.close()

    return inserted_total


def count_meter_rows() -> int:
    """Return the number of rows currently in meters."""
    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM meters")
            return cursor.fetchone()[0]
    finally:
        connection.close()


def report_metadata_summary(rows: list[dict]) -> None:
    """Print what the generator produced, before it is inserted.

    This is a cheap way to catch a problem early. The assignment states 4,000
    meters, 10 regions of 400 each, and a power factor of 0.95. If the printed
    figures disagree with those, something is wrong and it is far cheaper to
    notice here than after a 4,000-row insert.

    We are checking the generator's OUTPUT, not inventing data: these values come
    from meter_metadata() and are never written back into it.
    """
    print(f"  meters returned          {len(rows)}")
    print(f"  generator version        {smart_meter_simulator.dataset_info()['generator_version']}")

    regions: dict[str, int] = {}
    customer_types: dict[str, int] = {}
    power_factors: dict[float, int] = {}

    for meter in rows:
        regions[meter["region"]] = regions.get(meter["region"], 0) + 1
        customer_types[meter["customer_type"]] = customer_types.get(meter["customer_type"], 0) + 1
        power_factors[meter["power_factor"]] = power_factors.get(meter["power_factor"], 0) + 1

    print(f"  distinct regions         {len(regions)}")
    # Sort region names by their number, not as text. As text, 'Region 10' would
    # sort before 'Region 2' and the printout would look wrong.
    for region in sorted(regions, key=lambda name: int(name.split()[-1])):
        print(f"      {region:<10} {regions[region]:>5} meters")

    print(f"  distinct customer types  {len(customer_types)}")
    for customer_type in sorted(customer_types):
        print(f"      {customer_type:<12} {customer_types[customer_type]:>5} meters")

    print(f"  distinct power factors   {len(power_factors)}")
    for power_factor in sorted(power_factors):
        print(f"      {power_factor:<12} {power_factors[power_factor]:>5} meters")


def main() -> None:
    """Load the meters table, then verify the count."""
    print("=" * 78)
    print("Section 1.2  Load meter metadata")
    print(f"Started {cat_text()} CAT")
    print("=" * 78)

    expected_count = read_expected_meter_count()
    print("")
    print(f"  Generator declares {expected_count} meters")
    # --- Step 1: ask the generator for the metadata -----------------------------
    print("")
    print("Calling meter_metadata() from the unchanged generator")
    metadata_rows = smart_meter_simulator.meter_metadata()

    if len(metadata_rows) != expected_count:
        # Stop here. Loading the wrong number of rows would make the Section 1.2
        # verification pass or fail for the wrong reason.
        raise SystemExit(
            f"Generator returned {len(metadata_rows)} meters but dataset_info() "
            f"declares {expected_count}. Stopping before the insert."
        )

    print("")
    print("Metadata summary:")
    report_metadata_summary(metadata_rows)

    # --- Step 2: refuse to double-load ------------------------------------------
    existing_count = count_meter_rows()
    print("")
    if existing_count > 0:
        raise SystemExit(
            f"meters already contains {existing_count} rows.\n"
            "Refusing to insert again, because that would fail on the meter_id "
            "primary key.\n"
            "If a full reload is what you want, run:\n"
            "    python ingestion\\load_meters.py --reset"
        )
    print(f"  meters currently holds   {existing_count} rows, so it is safe to load")

    # --- Step 3: insert ----------------------------------------------------------
    print("")
    inserted_total = load_meter_rows(metadata_rows, reset=False)

    # --- Step 4: verify ----------------------------------------------------------
    final_count = count_meter_rows()

    print("")
    print("=" * 78)
    print("VERIFICATION")
    print("=" * 78)
    print(f"  rows inserted by this program  {inserted_total}")
    print(f"  rows now in meters             {final_count}")
    print(f"  expected                       {expected_count}")

    if final_count == expected_count:
        print("")
        print(f"  PASS: meters contains exactly {expected_count} rows, as Section 1.2 requires.")
    else:
        raise SystemExit(
            f"  FAIL: meters contains {final_count} rows but {expected_count} were expected."
        )

    print("")
    print("Confirm independently with SQL:")
    print('  docker exec -it timescaledb psql -U auca -d smart_energy_grid -c "SELECT count(*) FROM meters;"')
    print("")
    print("Sample rows:")
    print("  docker exec -it timescaledb psql -U auca -d smart_energy_grid -c \"SELECT * FROM meters ORDER BY meter_id LIMIT 5;\"")


if __name__ == "__main__":
    # --reset is the only option today, and it is off by default so that an
    # accidental re-run cannot destroy loaded data.
    parser = argparse.ArgumentParser(
        description="Load the 4,000 meter metadata rows into the meters table."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="TRUNCATE meters before loading. Needed only when reloading.",
    )
    arguments = parser.parse_args()

    if arguments.reset:
        # TRUNCATE then insert, so this is one call rather than two code paths.
        def main_with_reset() -> None:
            """Run main() after clearing the table."""
            existing = count_meter_rows()
            print(f"meters currently holds {existing} rows, which --reset will clear")
            main()

        run_with_log("meters_load_reset", main_with_reset)
    else:
        run_with_log("meters_load", main)