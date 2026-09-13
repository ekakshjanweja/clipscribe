"""Start a local Postgres (pgserver-bundled binaries) on 127.0.0.1:5544."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PGDATA = ROOT / ".cache" / "pgdata"
PORT = "5544"
USER = "clipscribe"
PASSWORD = "clipscribe-local"
DB = "clipscribe"

sys.path.insert(0, str(ROOT / ".venv" / "lib" / "python3.12" / "site-packages"))
import pgserver  # noqa: E402


def main() -> None:
    PGDATA.parent.mkdir(parents=True, exist_ok=True)
    if not (PGDATA / "PG_VERSION").exists():
        print("initdb ...", flush=True)
        pgserver.initdb(["-U", USER, "--auth=trust", "-E", "UTF8"], pgdata=PGDATA)
        with open(PGDATA / "postgresql.conf", "a", encoding="utf-8") as fh:
            fh.write("\nlisten_addresses = '127.0.0.1'\nport = 5544\n")
    try:
        status = pgserver.pg_ctl(["status"], pgdata=PGDATA)
        running = "no server running" not in status
    except subprocess.CalledProcessError:
        running = False
    if not running:
        print("starting postgres ...", flush=True)
        pgserver.pg_ctl(["-w", "-t", "60", "-l", str(PGDATA / "server.log"), "start"], pgdata=PGDATA)
    else:
        print("postgres already running", flush=True)
    dbs = pgserver.psql(
        ["-h", "127.0.0.1", "-p", PORT, "-U", USER, "-d", "postgres", "-tAc",
         f"SELECT 1 FROM pg_database WHERE datname='{DB}'"]
    ).strip()
    if dbs != "1":
        print(f"creating database {DB} ...", flush=True)
        pgserver.psql(["-h", "127.0.0.1", "-p", PORT, "-U", USER, "-d", "postgres", "-c", f"CREATE DATABASE {DB}"])
    pgserver.psql([
        "-h", "127.0.0.1", "-p", PORT, "-U", USER, "-d", "postgres", "-c",
        f"ALTER USER {USER} WITH PASSWORD '{PASSWORD}'",
    ])
    print(f"DATABASE_URL=postgresql://{USER}:{PASSWORD}@127.0.0.1:{PORT}/{DB}", flush=True)


if __name__ == "__main__":
    main()
