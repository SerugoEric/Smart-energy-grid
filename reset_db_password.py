import subprocess
import config

password = config.DB_PASSWORD.replace("'", "''")

sql = f"ALTER ROLE auca PASSWORD '{password}';"

subprocess.run(
    [
        "docker",
        "exec",
        "-i",
        "timescaledb",
        "psql",
        "-U",
        "auca",
        "-d",
        "smart_energy_grid",
        "-c",
        sql,
    ],
    check=True,
)

print("Database password updated successfully.")