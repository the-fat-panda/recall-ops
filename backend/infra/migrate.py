"""Run the Phase 1 CockroachDB schema migration."""

from __future__ import annotations

from pathlib import Path

from backend.infra.db import query

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def run_migration() -> None:
    """Execute the deliberately simple, semicolon-delimited Phase 1 DDL file."""
    statements = [statement.strip() for statement in SCHEMA_PATH.read_text().split(";")]
    for statement in statements:
        # SQL comments alone are harmless, but skipping them avoids unnecessary calls.
        if statement and any(line.strip() and not line.lstrip().startswith("--") for line in statement.splitlines()):
            query(statement)


if __name__ == "__main__":
    run_migration()
    print("RecallOps Phase 1 schema is ready.")
