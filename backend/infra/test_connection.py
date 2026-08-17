"""Minimal live CockroachDB connectivity check for Phase 1."""

from backend.infra.db import confirm_connection


if __name__ == "__main__":
    print(f"CockroachDB version: {confirm_connection()}")
