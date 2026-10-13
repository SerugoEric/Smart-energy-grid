"""Section 1.1 evidence collector: record the machine, containers and software.

PURPOSE
    Subsection 1.1 asks us to record and screenshot the environment before any
    data work begins: CPU, RAM, operating system, storage type, and the versions
    of Python, EMQX, PostgreSQL and TimescaleDB. It also asks for four specific
    PostgreSQL settings and a plain statement of whether PostgreSQL runs natively,
    in a container, or in a virtual machine, including any CPU or RAM limits.

    This program gathers that evidence automatically, so the numbers in the report
    are measured rather than guessed.

ENVIRONMENT THIS SCRIPT WAS WRITTEN FOR
    - Windows host
    - PostgreSQL 18.6 + TimescaleDB 2.30.2 in a Docker container "timescaledb",
      published on host port 5433
    - EMQX 6.3.1 in a Docker container "emqx"
    - A native Windows PostgreSQL 18 service also exists and is NOT used

    Because PostgreSQL runs in a container, three things need care:
      * RAM and CPU limits come from Docker, not from the host alone.
      * The PostgreSQL data directory is a path INSIDE the container, so free
        space there cannot be measured from the host. We ask the container.
      * The real CPU model name is available from Windows, not from Python.

INPUTS
    - config.py (via common.db.load_config) for connection settings
    - a running PostgreSQL container with the smart_energy_grid database
    - a reachable EMQX broker, for its version string
    - the docker command line tool, for container limits

OUTPUTS
    - a readable report printed to the terminal, suitable for a screenshot
    - the same report written to logs/environment_capture_<timestamp>.txt

HOW TO RUN
    From the project root:

        python ingestion\\capture_environment.py

    Take the screenshot from the terminal, keeping the taskbar and the clock
    visible, as Section 1.1.3 requires.

WHAT THIS PROGRAM CANNOT KNOW ON ITS OWN
    Whether a disk is SSD or HDD is not exposed to a plain Python program on
    Windows. The script prints the PowerShell command that reports it; paste that
    output into report/environment_details.md next to the printed values.
"""

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# WHY we add the project root to sys.path: this file lives in ingestion/ and the
# shared helpers live in common/. Importing the project as a package from another
# working directory would fail, so make the root explicit and predictable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.cat_time import CAT, cat_now, cat_text  # noqa: E402
from common.db import (  # noqa: E402
    PROJECT_ROOT,
    connect,
    fetch_dicts,
    load_config,
    machine_identifier,
    timestamped_log_path,
)

# The four PostgreSQL settings named in Section 1.1.2. Section 6 and Section 7
# results also depend on these, so we print them with SHOW exactly as the
# assignment words it.
REQUIRED_PG_SETTINGS = [
    "shared_buffers",
    "work_mem",
    "max_parallel_workers_per_gather",
    "jit",
]

# Extra settings recorded as context for the Section 3 and 4 timing discussions.
EXTRA_PG_SETTINGS = [
    "max_worker_processes",
    "maintenance_work_mem",
    "effective_cache_size",
    "max_wal_size",
    "random_page_cost",
    "max_connections",
]

# Candidate status endpoints, newest path first. EMQX 5 and 6 differ here, and we
# cannot be sure which one a given release exposes, so we try them in order.
EMQX_STATUS_PATHS = ["/api/v6/status", "/api/v5/status", "/status"]


# ---------------------------------------------------------------------------
# Small output helpers
# ---------------------------------------------------------------------------
def show(label: str, value) -> None:
    """Print one aligned 'label : value' line, the basic unit of our report."""
    print(f"  {label:<38} {value}")


def heading(text: str) -> None:
    """Print a section heading so each block is obvious in a screenshot."""
    print("")
    print("=" * 78)
    print(text)
    print("=" * 78)


def run_command(command: list[str], timeout: int = 20) -> tuple[int, str]:
    """Run a command and return its exit code and combined output.

    WHY A LIST AND NOT A STRING
        Passing a list means no shell is involved, so no quoting rules apply and
        a value containing a space cannot turn into two arguments.
    """
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return -1, f"{command[0]} was not found on PATH"
    except subprocess.TimeoutExpired:
        return -1, f"{command[0]} timed out after {timeout} seconds"
    except OSError as error:
        return -1, str(error)

    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def powershell(command: str) -> tuple[int, str]:
    """Run one PowerShell command and return its exit code and output.

    WHY -NoProfile: a PowerShell profile can print banners, change the output
    format or prompt for input, none of which we want inside a captured report.
    """
    return run_command(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
        ]
    )


# ---------------------------------------------------------------------------
# Machine facts
# ---------------------------------------------------------------------------
def windows_memory_status() -> dict:
    """Return host RAM total in bytes and the load percentage, via the Windows API.

    THE API NAME IS GlobalMemoryStatusEx, NOT GlobalMemorySizeEx
        Windows exports GlobalMemoryStatusEx, which takes a pointer to a
        MEMORYSTATUSEX structure and fills it in. There is no
        GlobalMemorySizeEx export, so asking ctypes for it raises AttributeError.
        That is why an earlier version of this script printed no RAM figure.

    WHY c_size_t AND NOT c_ulonglong
        The ul* fields of MEMORYSTATUSEX are of type SIZE_T. On 64-bit Windows
        that is 8 bytes, but on 32-bit it is 4, so a hard-coded 8-byte type
        would corrupt the structure. c_size_t is correct on both.

    WHY THE SIGNATURES ARE DECLARED
        Without argtypes and restype, ctypes assumes an int return and a default
        pointer size, which can truncate the pointer on a 64-bit host.
    """
    import ctypes

    class MemoryStatusEx(ctypes.Structure):
        """Mirror of the Windows MEMORYSTATUSEX structure. Field order matters."""

        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_size_t),
            ("ullAvailPhys", ctypes.c_size_t),
            ("ullTotalPageFile", ctypes.c_size_t),
            ("ullAvailPageFile", ctypes.c_size_t),
            ("ullTotalVirtual", ctypes.c_size_t),
            ("ullAvailVirtual", ctypes.c_size_t),
            ("ullAvailExtendedVirtual", ctypes.c_size_t),
        ]

    status = MemoryStatusEx()
    # dwLength must be set to the size of the structure before the call, or
    # Windows rejects it.
    status.dwLength = ctypes.sizeof(MemoryStatusEx)

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatusEx)]
    kernel32.GlobalMemoryStatusEx.restype = ctypes.c_int

    succeeded = kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    if not succeeded:
        raise OSError(ctypes.get_error_message(ctypes.get_last_error()))

    return {
        "total": int(status.ullTotalPhys),
        "load_percent": int(status.dwMemoryLoad),
    }


def total_ram_bytes() -> int:
    """Return installed host RAM in bytes, or raise OSError if it cannot be read.

    This is the platform-neutral entry point: it hides whether we are on Windows
    or on Linux, so the rest of the script never has to care.
    """
    if platform.system() == "Windows":
        return windows_memory_status()["total"]

    # Linux and macOS: /proc/meminfo reports MemTotal in kibibytes.
    with open("/proc/meminfo", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    raise OSError("MemTotal not found in /proc/meminfo")


def windows_processor_facts() -> dict:
    """Return CPU name, physical cores and logical processors from Windows.

    WHY NOT JUST platform.processor()
        On Windows, platform.processor() usually returns a generic family string
        such as "Intel64 Family 6 Model 158 Stepping 10", not the marketing name
        such as "Intel Core i7-12700". Section 1.1.2 asks for the CPU model, so we
        ask Windows directly through Win32_Processor.

    WHY ONE CALL FOR ALL THREE VALUES
        Each PowerShell start-up costs about a second. Collecting the name and
        both core counts in one call keeps the capture quick, and returning them
        pipe-separated avoids parsing formatted table output.
    """
    facts = {"cpu_name": None, "physical_cores": None, "logical_processors": None}

    code, output = powershell(
        "$p = Get-CimInstance Win32_Processor | Select-Object -First 1; "
        '"$($p.Name)|$($p.NumberOfCores)|$($p.NumberOfLogicalProcessors)"'
    )
    if code == 0 and "|" in output:
        name, physical, logical = output.strip().split("|")[:3]
        facts["cpu_name"] = name.strip()
        facts["physical_cores"] = physical.strip()
        facts["logical_processors"] = logical.strip()
        return facts

    # Fallback 1: the environment variable Windows always sets, which is still
    # more informative than platform.processor() on some builds.
    identifier = os.environ.get("PROCESSOR_IDENTIFIER")
    if identifier:
        facts["cpu_name"] = identifier

    return facts


def collect_machine_facts() -> None:
    """Print CPU, RAM and machine identity."""
    heading("1.1.2  MACHINE HARDWARE")

    show("Machine identifier", machine_identifier())
    show("Operating system", f"{platform.system()} {platform.release()}")
    show("OS version", platform.version())
    show("OS architecture", platform.architecture()[0])

    processor = windows_processor_facts()
    show("CPU model (Win32_Processor)", processor["cpu_name"] or "see PowerShell below")
    show("Physical cores", processor["physical_cores"] or "not reported")
    show("Logical processors", processor["logical_processors"] or os.cpu_count())

    try:
        memory = windows_memory_status()
        if memory:
            show("Host installed RAM", f"{memory['total'] / (1024 ** 3):.2f} GB")
            # The load percentage is a second view of memory pressure, which
            # matters when we interpret a slow benchmark run later.
            show("HostMemoryLoadPercent", f"{memory['load_percent']}%")
        else:
            show("Host installed RAM", f"{total_ram_bytes() / (1024 ** 3):.2f} GB")
    except OSError as error:
        show("Host installed RAM", f"could not be read: {error}")

    print("")
    print("  For the SSD or HDD type, run this and paste the output into")
    print("  report/environment_details.md:")
    print("")
    print("    Get-PhysicalDisk | Select-Object FriendlyName, MediaType, Size")


# ---------------------------------------------------------------------------
# Docker facts
# ---------------------------------------------------------------------------
def docker_running_containers() -> list[dict]:
    """Return one dict per running Docker container.

    The separator is a pipe because container names, images and ports cannot
    contain one, which makes splitting safe.
    """
    code, output = run_command(
        ["docker", "ps", "--format", "{{.Names}}|{{.Image}}|{{.Ports}}|{{.Status}}"]
    )
    if code != 0:
        return []

    containers = []
    for line in output.splitlines():
        parts = line.strip().split("|")
        if len(parts) < 4:
            continue
        containers.append(
            {
                "name": parts[0],
                "image": parts[1],
                "ports": parts[2],
                "status": parts[3],
            }
        )
    return containers


def find_container_by_hint(containers: list[dict], configured_name: str,
                           host_port: str, image_keywords: tuple[str, ...]) -> str | None:
    """Guess which container holds a service, and return its name.

    The search order is deliberate:
      1. an explicit name in config.py, because a human answer beats a guess;
      2. a container publishing the host port we connect to, which is the most
         reliable signal we actually hold, since we connect to that port;
      3. a container whose image name contains a keyword.

    The caller passes the container list in so docker ps runs once per capture
    rather than once per guess.
    """
    if configured_name:
        return configured_name

    for container in containers:
        if f":{host_port}->" in container["ports"]:
            return container["name"]

    for container in containers:
        image = container["image"].lower()
        if any(keyword in image for keyword in image_keywords):
            return container["name"]

    return None


def docker_inspect(container_name: str) -> dict | None:
    """Return the full docker inspect document for one container, or None.

    WHY THE WHOLE DOCUMENT IN ONE CALL
        We need the image, the CPU and memory limits, the cpuset and the mounts.
        Asking once for the full JSON is cheaper and simpler than five --format
        calls, and it means one point of failure instead of five.
    """
    code, output = run_command(["docker", "inspect", container_name])
    if code != 0:
        return None
    try:
        document = json.loads(output)
    except json.JSONDecodeError:
        return None
    if not document:
        return None
    return document[0]


def describe_container_limits(container_name: str) -> dict | None:
    """Return the CPU and memory limits Docker enforces on a container."""
    document = docker_inspect(container_name)
    if document is None:
        return None

    host_config = document.get("HostConfig", {}) or {}
    nano_cpus = int(host_config.get("NanoCpus") or 0)
    memory_bytes = int(host_config.get("Memory") or 0)
    cpu_quota = host_config.get("CpuQuota") or 0
    cpu_period = host_config.get("CpuPeriod") or 0

    limits = {
        "status": (document.get("State") or {}).get("Status", "unknown"),
        "image": (document.get("Config") or {}).get("Image", "unknown"),
        "nano_cpus": nano_cpus,
        "cpu_limit": f"{nano_cpus / 1_000_000_000:.2f} CPUs" if nano_cpus else "not limited by NanoCpus",
        "cpu_quota": f"{cpu_quota}/{cpu_period} period" if cpu_quota else "no quota",
        "cpuset": host_config.get("CpusetCpus") or "not set",
        "memory_bytes": memory_bytes,
        "memory_limit": f"{memory_bytes / (1024 ** 3):.2f} GB" if memory_bytes else "not limited",
        "memory_reservation": host_config.get("MemoryReservation") or 0,
        "mounts": document.get("Mounts") or [],
    }
    return limits


def report_docker_stats() -> None:
    """Print live CPU and memory use for every running container.

    WHY THIS MATTERS FOR THE REPORT
        Section 1.1.2 asks for the CPU and RAM limits in force. These limits are
        the reason a benchmark can be slower than the hardware suggests, so they
        belong in the report next to the timings.
    """
    code, output = run_command(
        [
            "docker", "stats", "--no-stream",
            "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}",
        ]
    )
    if code != 0:
        print("  docker stats unavailable")
        return

    for line in output.splitlines():
        parts = line.strip().split("|")
        if len(parts) < 4:
            continue
        print(f"  {parts[0]:<24} CPU {parts[1]:<8} MEM {parts[2]:<18} {parts[3]}")


def report_wsl_limits() -> None:
    """Print the WSL memory and CPU settings when WSL is in use.

    Section 1.1.2 asks whether the database runs in a virtual machine. WSL is a
    virtual machine, and its limits come from %USERPROFILE%\\.wslconfig, not from
    Windows itself, so the file is worth reading and quoting in the report.
    """
    config_file = os.path.join(os.path.expanduser("~"), ".wslconfig")
    if not os.path.exists(config_file):
        return

    print("")
    print("  WSL is configured in .wslconfig, which caps memory and processors:")
    try:
        with open(config_file, encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                # Only the resource limits matter for our measurements, so we show
                # the memory and processor lines and skip the rest of the file.
                if stripped.lower().startswith(("memory", "processors", "swap")):
                    print(f"    {stripped}")
    except OSError as error:
        print(f"    could not read {config_file}: {error}")


def report_virtualization(settings: dict) -> str | None:
    """Print how the services are hosted, and return the PostgreSQL container name."""
    heading("1.1.2  NATIVE, CONTAINER OR VIRTUAL MACHINE")

    # WHY NO FALLBACK PORT: guessing a port would send us to the wrong server.
    # The native Windows PostgreSQL service listens on 5432 while the container
    # we use is published on 5433, so a silent default here could quietly
    # produce a report full of numbers from the wrong installation.
    if "DB_PORT" not in settings:
        raise SystemExit(
            "DB_PORT is missing from config.py.\n"
            "Copy config.example.py to config.py and set DB_PORT to the published "
            "host port of the timescaledb container."
        )
    database_port = str(settings["DB_PORT"])
    containers = docker_running_containers()
    container_name = find_container_by_hint(
        containers,
        configured_name=str(settings.get("PG_CONTAINER_NAME", "") or ""),
        host_port=database_port,
        image_keywords=("timescale", "postgres"),
    )

    if not containers:
        print("  docker ps returned nothing. Either Docker is not running or the")
        print("  services are native. State the arrangement manually in the report.")
        return container_name

    print("  Running containers:")
    for container in containers:
        print(f"    {container['name']:<20} {container['image']:<40} {container['status']}")
        if container["ports"]:
            print(f"    {'':<20} ports: {container['ports']}")

    print("")
    print(f"  PostgreSQL container: {container_name or 'NOT DETECTED'}")

    if container_name:
        limits = describe_container_limits(container_name)
        if limits:
            show("Container status", limits["status"])
            show("Container image", limits["image"])
            show("CPU limit (NanoCpus)", limits["cpu_limit"])
            show("CPU quota / period", limits["cpu_quota"])
            show("CPU set (cpuset)", limits["cpuset"])
            show("Memory limit", limits["memory_limit"])
            show("Memory limit bytes", limits["memory_bytes"] or "0 means unlimited")
            show("Memory reservation", limits["memory_reservation"] or "not set")

            print("")
            print("  Volume mounts:")
            for mount in limits["mounts"]:
                print(
                    f"    {mount.get('Type', '?'):<8} "
                    f"{mount.get('Source', '?')} -> {mount.get('Destination', '?')}"
                )

    print("")
    print("  Live docker stats:")
    report_docker_stats()

    report_wsl_limits()

    return container_name


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
def collect_storage_facts(settings: dict, database_container: str | None) -> None:
    """Print free space where the project and the database will live.

    WHY THE CONTAINER IS INVOLVED
        The PostgreSQL data directory reported by the server is a path INSIDE the
        container, so shutil.disk_usage cannot open it from the host. We therefore
        run df inside the container, which measures the filesystem that actually
        holds the tables.

    WHY FREE SPACE MATTERS HERE
        Section 2 loads about 10.7M rows. Section 3 keeps three uncompressed
        copies and Section 4 adds two more tables, and 4.1.6 says to keep all
        five. Finding the space limit now is much cheaper than discovering it
        halfway through Section 4.
    """
    heading("1.1.2  STORAGE AND CLOCK")

    show("Project folder", PROJECT_ROOT)
    try:
        usage = shutil.disk_usage(PROJECT_ROOT)
        show("Project disk total", f"{usage.total / (1024 ** 3):.2f} GB")
        show("Project disk free", f"{usage.free / (1024 ** 3):.2f} GB")
    except OSError as error:
        show("Project disk free", f"unreadable: {error}")

    if database_container:
        print("")
        print(f"  Free space inside the {database_container} container:")
        code, output = run_command(
            ["docker", "exec", database_container, "df", "-h", "/var/lib/postgresql/data"]
        )
        if code == 0:
            for line in output.splitlines():
                print(f"    {line}")
        else:
            code, output = run_command(["docker", "exec", database_container, "df", "-h", "/"])
            if code == 0:
                for line in output.splitlines():
                    print(f"    {line}")
            else:
                print(f"    df unavailable inside the container: {output.strip()}")

    show("Current time (CAT)", cat_text(cat_now()))
    show("Current time (UTC)", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    show("Report time zone", str(CAT))

    print("")
    print("  Section 1.1.3 requires the machine clock to be synchronised.")
    print("  Run this and paste the result into report/environment_details.md:")
    print("")
    print("    w32tm /query /status")


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
def probe_postgres(settings: dict) -> None:
    """Connect to the assignment database and print versions and settings.

    A failure here is expected on a first run if the database has not been created
    yet, so the error is reported as a fact rather than raised. That way one
    missing service does not hide the machine details printed above.
    """
    heading("1.1.2  POSTGRESQL AND TIMESCALEDB VERSIONS")

    show("Configured host and port", f"{settings.get('DB_HOST')}:{settings.get('DB_PORT')}")
    show("Configured database", settings.get("DB_NAME"))
    show("Configured user", settings.get("DB_USER"))

    connection = None
    try:
        connection = connect(application_name="capture_environment")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT current_database()   AS connected_database,
                       current_user         AS connected_user,
                       current_setting('TimeZone') AS session_timezone,
                       version()             AS server_version_text
                """
            )
            row = fetch_dicts(cursor)[0]
            show("Connected database", row["connected_database"])
            show("Connected user", row["connected_user"])
            show("Session time zone", row["session_timezone"])

            # Split "PostgreSQL 18.6 (Debian ...), compiled by ..." into just the
            # version, because the platform part is already reported above.
            show("Server version", row["server_version_text"].split(" on ")[0].split(",")[0])

            # The four required settings, read with SHOW so the report quotes the
            # exact command the assignment names. Names come from the module-level
            # list above, never from user input, so building SQL by string
            # formatting is safe here.
            print("")
            print("  Required PostgreSQL settings (Section 1.1.2):")
            for name in REQUIRED_PG_SETTINGS:
                cursor.execute(f"SHOW {name}")
                show(f"    {name}", cursor.fetchone()[0])

            print("")
            print("  Additional settings recorded as context for Sections 3 and 4:")
            for name in EXTRA_PG_SETTINGS:
                cursor.execute(f"SHOW {name}")
                show(f"    {name}", cursor.fetchone()[0])

            # The time zone, seen from inside a live session. This is the value
            # common.db.connect() sets for every program in the project.
            cursor.execute("SELECT now() AS shown_in_session_tz, "
                           "       now() AT TIME ZONE 'Africa/Kigali' AS shown_in_cat")
            row = fetch_dicts(cursor)[0]
            print("")
            print("  Time zone check (both values describe the same instant):")
            show("    now() in session time zone", str(row["shown_in_session_tz"]))
            show("    same instant in CAT", str(row["shown_in_cat"]))

            # Where the data lives. Section 2 needs this to plan disk space, and
            # the path is inside the container when PostgreSQL is containerised.
            cursor.execute("SELECT current_setting('data_directory') AS data_dir")
            data_dir = fetch_dicts(cursor)[0]["data_dir"]
            show("", "")
            show("PostgreSQL data directory", data_dir)
            show("  (this path is inside the container,", "so only the container can report its free space)")

            # Current database size, so we have a starting point before 10.7M rows.
            cursor.execute(
                "SELECT pg_size_pretty(pg_database_size(current_database())) AS pretty_size, "
                "       pg_database_size(current_database()) AS size_bytes"
            )
            row = fetch_dicts(cursor)[0]
            show("Database size now", row["pretty_size"])

            # TimescaleDB presence and version.
            cursor.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"
            )
            installed = cursor.fetchone()
            version_text = installed[0] if installed else None
            show("TimescaleDB installed version", version_text or "NOT INSTALLED")

            cursor.execute(
                "SELECT default_version FROM pg_available_extensions WHERE name = 'timescaledb'"
            )
            available = cursor.fetchone()
            show("TimescaleDB default version", available[0] if available else "unknown")

            # Compare the running version with the 2.10 minimum, part by part.
            # A string comparison would be wrong: "2.9" is greater than "2.10"
            # alphabetically, because "9" sorts after "1".
            if version_text:
                try:
                    major_text, minor_text = version_text.split(".")[0:2]
                    running = (int(major_text), int(minor_text))
                    show("Meets TimescaleDB >= 2.10", "YES" if running >= (2, 10) else "NO")
                    if running < (2, 10):
                        print("  Section 1.1 requires 2.10 or later. Upgrade before continuing.")
                except ValueError:
                    print("  Could not parse the TimescaleDB version string.")

            # The compression settings available right now. Section 4 has to use
            # the syntax this build understands, and 2.18 renamed compression to
            # columnstore, so we read the list rather than assume.
            cursor.execute(
                "SELECT name FROM pg_settings "
                "WHERE name LIKE 'timescaledb.compress%' "
                "   OR name LIKE 'timescaledb.enable_columnstore%' "
                "   OR name LIKE '%columnstore%' "
                "ORDER BY name"
            )
            names = [row["name"] for row in fetch_dicts(cursor)]
            print("")
            print("  Columnstore / compression settings this build exposes:")
            if names:
                for name in names:
                    print(f"    {name}")
            else:
                print("    none found by name; Section 4 will inspect the schema instead")
    except Exception as error:  # noqa: BLE001 - a database problem must not hide the rest
        print(f"  PostgreSQL probe failed: {error}")
        print("  Check that the timescaledb container is up, that port")
        print(f"  {settings.get('DB_PORT')} is published, and that smart_energy_grid exists")
        print("  (run sql/00_create_database.sql).")
    finally:
        # WHY close explicitly: the connection context manager commits the
        # transaction but leaves the socket open, holding a backend slot.
        if connection is not None:
            connection.close()


# ---------------------------------------------------------------------------
# EMQX
# ---------------------------------------------------------------------------
def port_is_open(host: str, port: int, timeout: float = 3.0) -> bool:
    """Return True when a TCP connection to host:port succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def emqx_version_from_api(host: str, api_port: int) -> dict | None:
    """Return the EMQX status document from whichever endpoint answers."""
    for path in EMQX_STATUS_PATHS:
        url = f"http://{host}:{api_port}{path}"
        try:
            request = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            continue
        if isinstance(payload, dict):
            payload["_endpoint"] = path
            return payload
    return None


def probe_emqx(settings: dict) -> None:
    """Print EMQX reachability, version and container limits."""
    heading("1.1.2  EMQX BROKER VERSION")

    host = settings.get("MQTT_HOST", "localhost")
    mqtt_port = int(settings.get("MQTT_PORT", 1883))
    api_port = int(settings.get("EMQX_API_PORT", 18083))

    show("Broker host", host)
    show("MQTT port open", f"{mqtt_port} -> {port_is_open(host, mqtt_port)}")
    show("Dashboard port open", f"{api_port} -> {port_is_open(host, api_port)}")
    show("Dashboard URL", f"http://{host}:{api_port}")

    payload = emqx_version_from_api(host, api_port)
    if payload:
        show("Status endpoint", payload.get("_endpoint", "unknown"))
        for key in ("version", "node_name", "node_status", "uptime", "started_at"):
            if key in payload:
                show(f"EMQX {key}", payload[key])
    else:
        show("EMQX status endpoint", "no known status path answered")

    container_name = find_container_by_hint(
        docker_running_containers(),
        configured_name=str(settings.get("EMQX_CONTAINER_NAME", "") or ""),
        host_port=str(mqtt_port),
        image_keywords=("emqx",),
    )
    show("EMQX container", container_name or "not detected")

    if container_name:
        limits = describe_container_limits(container_name)
        if limits:
            show("EMQX container image", limits["image"])
            show("EMQX container status", limits["status"])
            show("EMQX CPU limit", limits["cpu_limit"])
            show("EMQX memory limit", limits["memory_limit"])

        # The API path varies between releases, so ctl inside the container is a
        # reliable second source for the version string.
        if payload is None or "version" not in payload:
            code, output = run_command(
                ["docker", "exec", container_name, "emqx", "ctl", "status"]
            )
            if code == 0:
                print("")
                print("  emqx ctl status:")
                for line in output.splitlines()[:12]:
                    print(f"    {line}")
            else:
                print("")
                print("  To read the EMQX version manually, run:")
                print(f"    docker exec {container_name} emqx ctl status")
                print(f"    docker logs {container_name} | Select-Object -First 20")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    """Collect every Section 1.1 fact, print it and save it to the logs folder."""
    started_at = cat_now()

    print("=" * 78)
    print("Section 1.1  Environment capture")
    print(f"Started {cat_text(started_at)} CAT")
    print("=" * 78)

    settings = load_config()

    print("")
    show("Project root", PROJECT_ROOT)
    show("Python version", sys.version.split()[0])
    show("Python executable", sys.executable)

    database_container = report_virtualization(settings)
    collect_machine_facts()
    collect_storage_facts(settings, database_container)
    probe_postgres(settings)
    probe_emqx(settings)

    finished_at = cat_now()
    heading("CAPTURE COMPLETE")
    show("Started (CAT)", cat_text(started_at))
    show("Finished (CAT)", cat_text(finished_at))
    show("Elapsed seconds", f"{(finished_at - started_at).total_seconds():.3f}")
    print("")
    print("Copy the block above into report/environment_details.md, then take the")
    print("four screenshots in that file's checklist, with the taskbar and the clock")
    print("visible in every one of them.")


if __name__ == "__main__":
    # WHY the tee: the same report must reach both the terminal, so it can be
    # screenshotted, and a log file, so the numbers can be pasted into the report
    # later without retyping them.
    log_path = timestamped_log_path("environment_capture")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = open(log_path, "w", encoding="utf-8")
    original_stdout = sys.stdout

    class TeeToFile:
        """Write to both the terminal and the log file."""

        def write(self, text: str) -> int:
            original_stdout.write(text)
            log_handle.write(text)
            return len(text)

        def flush(self) -> None:
            original_stdout.flush()
            log_handle.flush()

    sys.stdout = TeeToFile()
    try:
        main()
    finally:
        sys.stdout = original_stdout
        log_handle.close()

    print(f"Report also saved to {log_path}")