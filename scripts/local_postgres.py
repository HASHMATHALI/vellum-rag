"""Start (or attach to) a local embedded PostgreSQL 16 + pgvector server for development and tests.

Uses the `pgserver` package, so Docker is not required. Data lives in %LOCALAPPDATA%/vellum_pg
(or ~/.vellum_pg). Prints an asyncpg DATABASE_URL for each requested database.

Usage:
    python scripts/local_postgres.py                # ensures rag_dev and rag_test exist
    python scripts/local_postgres.py rag_eval       # additional databases
    python scripts/local_postgres.py --stop
"""
import os
import sys

import pgserver


def data_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "vellum_pg")


def main() -> None:
    args = sys.argv[1:]
    server = pgserver.get_server(data_dir(), cleanup_mode=None)
    if "--stop" in args:
        server.cleanup()
        print("stopped")
        return
    dbs = [a for a in args if not a.startswith("-")] or ["rag_dev", "rag_test"]
    existing = server.psql("SELECT datname FROM pg_database;")
    for db in dbs:
        if f" {db}\n" not in existing and f" {db} " not in existing:
            server.psql(f'CREATE DATABASE "{db}";')
        server.psql(f'\\c "{db}"\nCREATE EXTENSION IF NOT EXISTS vector;')
    uri = server.get_uri()  # postgresql://postgres:@127.0.0.1:PORT/postgres
    base = uri.rsplit("/", 1)[0].replace("postgresql://", "postgresql+asyncpg://")
    for db in dbs:
        print(f"{db}={base}/{db}")


if __name__ == "__main__":
    main()
