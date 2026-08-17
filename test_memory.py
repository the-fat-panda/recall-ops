"""Manual Phase 1 verification against the configured CockroachDB cluster."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

from backend.infra.db import confirm_connection, query
from backend.ingestion.seed import seed_database
from backend.memory.scoring import confidence, freshness
from backend.memory.search import search_incidents


def main() -> None:
    print(f"Connected: {confirm_connection()}")
    existing = query("SELECT count(*) AS count FROM incidents")[0]["count"]
    if not existing:
        print("Database is empty; loading the labelled synthetic corpus…")
        print(f"Loaded {seed_database()} synthetic incidents.")

    alert = "pods won't start after a config change"
    matches = search_incidents(alert, limit=5)
    print(f"\nAlert: {alert}\n\nTop matched past incidents:")
    for index, match in enumerate(matches, start=1):
        print(f"{index}. [{match['signature']}] similarity={match['similarity']:.3f}")
        print(f"   {match['description']}")

    if not matches:
        print("No incidents found. Run: python -m backend.ingestion.seed")
        return

    signature = matches[0]["signature"]
    current_version = os.getenv("CURRENT_ENV_VERSION")
    stats = query(
        """
        SELECT action, success_count, fail_count, last_success_at, last_env_version
        FROM fix_stats WHERE signature = %s ORDER BY success_count DESC, fail_count ASC, action ASC
        """,
        (signature,),
    )
    print(f"\nCandidate actions for {signature}:")
    for stat in stats:
        score = confidence(stat["success_count"], stat["fail_count"])
        recency = freshness(stat["last_success_at"], stat["last_env_version"], current_version)
        print(
            f"- {stat['action']}: success={stat['success_count']}, fail={stat['fail_count']}, "
            f"confidence={score:.2%}, freshness={recency:.2%}"
        )


if __name__ == "__main__":
    main()
