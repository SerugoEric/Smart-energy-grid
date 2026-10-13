"""Database connection helper for the Smart Energy Grid assignment.

PURPOSE
    Open a psycopg2 connection to the single assignment database with the
    session time zone already set to CAT, so no program has to repeat that
    setup and no program can accidentally load under a different zone.

INPUTS
    Settings from config.py, each overridable by an environment variable of
    the same name (see config.example.py).

OUTPUTS
    load_config()                 the resolved settings dictionary
    connect()                     a psycopg2 connection, CAT time zone set
    fetch_dicts(cursor)           query rows as list of dicts
    log_directory() / data_directory()  resolved absolute paths

HOW TO RUN
    Imported by the other programs:
        from common.db import connect, fetch_dicts
"""

import importlib.util
import os
import platform
from pathlib import Path

import psycopg2

# The project root is the parent of the folder holding this file. Resolving paths
# from here means a program works no matter which folder you launch it from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    """Return the settings from config.py, with environment variables winning.

    WHY THIS ORDER
        config.py is convenient for daily work. Environment variables are
        better for one-off commands, because they need no file edit and they
        leave no trace in the repository. Precedence: environment > config.py.
    """
    settings: dict = {}

    # --- read config.py if the student has created it ---
    config_path = PROJECT_ROOT / "config.py"
    if config_path.exists():
        spec = importlib.util.spec_from_file_location("config", config_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load settings from {config_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # Upper-case names are the convention for module-level constants, so we
        # pick up exactly those and ignore helper names and comments.
        for name in dir(module):
            if name.isupper():
                settings[name] = getattr(module, name)

    if not settings:
        raise SystemExit(
            "config.py was not found.\n"
            f"Create it with:  Copy-Item config.example.py config.py\n"
            f"Expected at:     {config_path}"
        )

    # --- environment variables override file values ---
    for name in list(settings):
        from_environment = os.environ.get(name)
        if from_environment:
            settings[name] = from_environment

    return settings


def log_directory() -> Path:
    """Return the absolute logs folder, creating it if needed."""
    from common.cat_time import cat_text  # local import avoids a circular import

    settings = load_config()
    folder = PROJECT_ROOT / settings.get("LOG_DIR", "logs")
    folder.mkdir(parents=True, exist_ok=True)
    # Filenames sort chronologically only if the timestamp comes first.
    return folder


def timestamped_log_path(prefix: str, suffix: str = ".txt") -> Path:
    """Return a unique log filename like logs/pilot_2026-10-05_10-30-00.txt.

    WHY a timestamp in the name: several runs of the same program must not
    overwrite each other. Colons are illegal in Windows filenames, so the time
    part uses hyphens.
    """
    from common.cat_time import cat_now

    stamp = cat_now().strftime("%Y-%m-%d_%H-%M-%S")
    return log_directory() / f"{prefix}_{stamp}{suffix}"


def data_directory() -> Path:
    """Return the absolute data folder for CSV captures, creating it if needed."""
    settings = load_config()
    folder = PROJECT_ROOT / settings.get("DATA_DIR", "data")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def machine_identifier() -> str:
    """Return a short stable label for this machine, used in timing records.

    Section 3.2.3 requires a machine identifier with every measured run. We use
    the hostname, because it appears in pg_stat_activity and in EXPLAIN output
    and therefore ties a SQL result back to the client that produced it.
    """
    return f"{platform.node() or 'unknown-host'}/{platform.machine() or 'unknown-arch'}"


def connect(dbname: str | None = None, autocommit: bool = False,
            application_name: str | None = None):
    """Open a connection to the assignment database with the session time zone CAT.

    WHY SET TIME ZONE HERE
        Section 1.1 requires the session time zone to be Africa/Kigali. Doing it
        inside this helper means every program in the project inherits it. It is
        a session setting, so it is re-sent on each new connection rather than
        trusted from the database default alone.

    Parameters
        dbname            override the configured database name
        autocommit        True for read-only queries and DDL that cannot run in a
                          transaction, such as CREATE DATABASE
        application_name  visible in pg_stat_activity, which is how the benchmark
                          tables record which client ran each query

    Returns
        An open psycopg2 connection.
    """
    settings = load_config()

    connection = psycopg2.connect(
        host=settings["DB_HOST"],
        port=int(settings["DB_PORT"]),
        dbname=dbname or settings["DB_NAME"],
        user=settings["DB_USER"],
        password=settings["DB_PASSWORD"],
        connect_timeout=int(settings.get("DB_CONNECT_TIMEOUT", 10)),
        application_name=application_name or settings.get("APP_NAME", "smart-energy-grid"),
    )
    connection.autocommit = autocommit

    if not autocommit:
        with connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'Africa/Kigali'")
        connection.commit()

    return connection


def fetch_dicts(cursor) -> list[dict]:
    """Return all remaining rows as a list of dicts keyed by column name.

    WHY THIS HELPER
        Analysing 10.6M rows needs the column names to survive the trip from
        SQL to Python. Without this, every query would need hand-written
        positional indexing, which breaks silently if a column is reordered.
    """
    # WHY getattr with a fallback: psycopg2 2.8 and newer expose the name as a
    # .name attribute, but the plain tuple form description[0] works on every
    # version. This keeps the helper usable if an older psycopg2 is installed.
    columns = [
        getattr(description, "name", description[0])
        for description in cursor.description
    ]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]