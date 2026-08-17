"""Apply the sandbox orders schema using the shared CockroachDB query helper."""

from __future__ import annotations

from pathlib import Path

from backend.infra.db import query

SCHEMA_PATH = Path(__file__).with_name("schema_orders.sql")


def run_orders_migration() -> None:
    """Execute the simple, semicolon-delimited sandbox schema file."""
    for statement in (part.strip() for part in SCHEMA_PATH.read_text().split(";")):
        if statement and any(line.strip() and not line.lstrip().startswith("--") for line in statement.splitlines()):
            query(statement)


if __name__ == "__main__":
    run_orders_migration()
    print("Orders sandbox schema is ready with five synthetic rows.")
