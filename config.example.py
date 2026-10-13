r"""Connection settings for the Smart Energy Grid assignment.

PURPOSE
    Hold every machine-specific setting in one place, so no program has a
    hard-coded host, port, database name, user or password inside it.

HOW TO USE
    1. Copy this file to  config.py  in the same folder:
           Copy-Item config.example.py config.py
    2. Open config.py and replace the PLACEHOLDER values.
    3. config.py is listed in .gitignore and must never be committed.

    If you already have a config.py with a real password in it, do NOT overwrite
    it. Just edit the few values below by hand inside your existing config.py.

WHY THE PLACEHOLDERS MATTER
    Section 9.2 submits this repository to GitHub and also as a ZIP. If a real
    password were committed, anyone could read it. Only placeholders go in.

NOTE ON BACKSLASHES
    This docstring starts with r""" on purpose. Without the r prefix, the text
    ingestion\load_meters.py inside it would be read as an escape sequence:
    Python treats \l as invalid, so Python 3.12 and later raise a
    SyntaxWarning while importing the file. A raw string keeps the text exactly
    as written. The same care applies to any docstring containing a Windows path.

INPUTS
    Nothing. This module only defines constants.

OUTPUTS
    The constants below, read by common.db.load_config().
"""

# --------------------------------------------------------------------------
# PostgreSQL / TimescaleDB
# --------------------------------------------------------------------------
# PostgreSQL 18.6 and TimescaleDB 2.30.2 run inside a Docker container named
# "timescaledb", published on host port 5433. The separate native Windows
# PostgreSQL 18 service is NOT used by this assignment; do not connect to it.
DB_HOST = "localhost"
DB_PORT = "5433"
DB_NAME = "smart_energy_grid"
DB_USER = "auca"
DB_PASSWORD = "PLACEHOLDER_PG_PASSWORD"

# Seconds to wait before giving up on a connection. A short timeout turns a
# misconfigured host into a clear error message instead of a long hang.
DB_CONNECT_TIMEOUT = "10"

# Reported by PostgreSQL in pg_stat_activity. Section 3.2.4 requires naming the
# client used for the SQL benchmarks, so every program sets this explicitly.
APP_NAME = "smart-energy-grid"

# Optional. If set, the environment script inspects this Docker container
# instead of guessing which one runs PostgreSQL. Leave empty to auto-detect by
# published host port.
PG_CONTAINER_NAME = ""

# --------------------------------------------------------------------------
# MQTT broker (EMQX)
# --------------------------------------------------------------------------
# EMQX 6.3.1 runs in a Docker container named "emqx".
MQTT_HOST = "localhost"
MQTT_PORT = "1883"
MQTT_KEEPALIVE = "60"

# EMQX also serves a web dashboard, which is where one of the Section 1.1
# screenshots comes from.
EMQX_DASHBOARD_PORT = "18083"
EMQX_API_PORT = "18083"

# Optional. Auto-detected when empty.
EMQX_CONTAINER_NAME = ""

# --------------------------------------------------------------------------
# Folders
# --------------------------------------------------------------------------
# Relative paths are resolved from the project root by the common/ helpers.
LOG_DIR = "logs"
DATA_DIR = "data"

# --------------------------------------------------------------------------
# Report settings
# --------------------------------------------------------------------------
# All dates and times in this assignment are CAT (Africa/Kigali, UTC+2).
REPORT_TIMEZONE = "Africa/Kigali"