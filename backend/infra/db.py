"""Small CockroachDB query helper used by Phase 1."""

from __future__ import annotations

import os
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, urlsplit

from dotenv import load_dotenv

load_dotenv()


def _database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required. Add it to .env or the environment.")
    return url


def database_url() -> str:
    """Return DATABASE_URL after validating its required TLS root certificate."""
    url = _database_url()
    options = parse_qs(urlsplit(url).query)
    sslmode = options.get("sslmode", [""])[0].lower()
    if sslmode in {"verify-full", "verify-ca"}:
        root_cert = options.get("sslrootcert", [""])[0]
        if not root_cert:
            raise RuntimeError(
                "sslrootcert is required when sslmode uses certificate verification; "
                "mount the CockroachDB CA certificate into the container."
            )
        if not os.path.exists(root_cert):
            raise RuntimeError(
                f"CockroachDB CA cert not found at {root_cert} — mount it into the container."
            )
    return url


def query(sql: str, params: Sequence[Any] | Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run one SQL statement and return result rows as dictionaries when present."""
    # Imported lazily so schema/text-only tooling does not require a live driver.
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(database_url(), autocommit=True, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall()) if cursor.description else []


def confirm_connection() -> str:
    """Import-test helper: verify DATABASE_URL by asking CockroachDB for its version."""
    version = query("SELECT version() AS version")[0]["version"]
    return str(version)


if __name__ == "__main__":
    print(confirm_connection())
