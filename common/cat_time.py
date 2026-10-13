"""CAT (Africa/Kigali) time helpers used by every program in this project.

PURPOSE
    The assignment states that all dates and times are CAT (Africa/Kigali,
    UTC+2). This module is the single place that knows how to produce a CAT
    timestamp, so a screenshot never shows an ambiguous or local-time clock.

INPUTS
    None. This module only reads the system clock and formats it.

OUTPUTS
    CAT              the tzinfo object for Africa/Kigali
    cat_now()        an aware datetime in CAT
    cat_text(when)   a "2026-10-05 10:30:00+02:00" string for printing
    cat_timer(label) a context manager that prints CAT start, CAT end and
                     elapsed milliseconds, used for every timing measurement

HOW TO RUN
    This module is imported, never run directly:
        from common.cat_time import cat_now, cat_text, cat_timer
"""

import time
from contextlib import contextmanager
from datetime import datetime

# WHY a try/except here: Python's zoneinfo reads the IANA time zone database,
# which Windows does not ship. Without the tzdata package this raises
# ZoneInfoNotFoundError. We catch it and print the exact fix instead of a
# traceback the student has to decode.
try:
    from zoneinfo import ZoneInfo

    CAT = ZoneInfo("Africa/Kigali")
except Exception as error:  # noqa: BLE001 - we re-raise with a clearer message
    raise SystemExit(
        "Could not load the Africa/Kigali time zone.\n"
        "Windows has no IANA time zone database, so install tzdata:\n"
        "    pip install tzdata\n"
        f"Original error: {error}"
    ) from error


def cat_now() -> datetime:
    """Return the current instant as an aware datetime in CAT."""
    return datetime.now(CAT)


def cat_text(when: datetime | None = None) -> str:
    """Format a CAT timestamp for logs and screenshots.

    WHY timespec="seconds": the assignment needs readable clock times in
    screenshots. Microseconds would be noise. A datetime in any other zone is
    converted to CAT first, so this is safe to call on UTC values.
    """
    if when is None:
        when = cat_now()
    if when.tzinfo is not None:
        when = when.astimezone(CAT)
    return when.isoformat(timespec="seconds")


@contextmanager
def cat_timer(label: str):
    """Print a CAT start time, a CAT end time and the elapsed milliseconds.

    Section 3.2.3 requires the CAT start and end of every measured run. Wrapping
    a statement in this context manager guarantees both are recorded by the same
    timer, which is what "use the same elapsed-time timer" means.

    Usage:
        with cat_timer("Q1 on energy_readings"):
            cursor.execute(query_sql)
            rows = cursor.fetchall()
    """
    # WHY two clocks: perf_counter is a monotonic high-resolution counter used
    # for the duration, while cat_now() gives the human-readable CAT wall clock.
    # Mixing them would be a bug; using perf_counter for elapsed time protects
    # against a clock adjustment or a daylight-saving jump distorting a duration.
    started_at = cat_now()
    started_counter = time.perf_counter()

    print(f"[{cat_text(started_at)}] START  {label}")

    try:
        yield started_at
    finally:
        # The finally block means the duration is printed even if the statement
        # raised an error, which is exactly when we want a timing record.
        elapsed_ms = (time.perf_counter() - started_counter) * 1000.0
        finished_at = cat_now()
        print(
            f"[{cat_text(finished_at)}] END    {label}  "
            f"duration_ms={elapsed_ms:.3f}"
        )