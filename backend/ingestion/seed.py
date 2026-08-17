"""Load a clearly labelled, synthetic Phase 1 ops-incident corpus."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from backend.ingestion.embedder import embed_batch
from backend.infra.db import query
from backend.infra.migrate import run_migration

SYNTHETIC_NAMESPACE = uuid.UUID("f3f290df-72b2-4edc-b20a-75776ec4a390")

# Synthetic data only: no descriptions, environments, or attempted remediations
# below originate from a real RecallOps customer or production incident.
SCENARIOS = {
    "CrashLoopBackOff": {
        "environment": "production-k8s-1.29.3",
        "descriptions": [
            "api deployment enters CrashLoopBackOff after ConfigMap rollout; logs show missing PAYMENT_GATEWAY_URL",
            "worker pods repeatedly restart after release 2025.06.14 because required Redis URL is absent",
            "checkout service crashes on startup after a Helm values change removed SESSION_SECRET",
            "notification consumer loops in CrashLoopBackOff following a malformed feature flag configuration",
            "billing deployment starts then exits because a newly required environment variable is unset",
            "gateway pods cannot stay running after config promotion; validation rejects empty OIDC issuer",
            "reporting service restarts immediately after secret mount name changed in the deployment manifest",
        ],
        "actions": [("rollback deployment to prior revision", "success"), ("restart affected pods", "fail"), ("restore missing configuration key", "success")],
    },
    "OOMKilled": {
        "environment": "production-k8s-1.29.3",
        "descriptions": [
            "image processor pods are OOMKilled while processing high-resolution uploads after release",
            "Java order service is killed for exceeding its memory limit during traffic spike",
            "ETL CronJob terminates OOMKilled after the nightly dataset grew beyond heap allocation",
            "search indexer restarts with OOMKilled while rebuilding a tenant index",
            "PDF rendering workers exceed cgroup memory limit under concurrent document load",
            "analytics consumer is OOMKilled after an unbounded batch accumulated in memory",
            "cache warmer pods are killed after the latest release increased object retention",
        ],
        "actions": [("increase container memory limit", "success"), ("restart affected pods", "fail"), ("reduce batch size and redeploy", "success")],
    },
    "OAuthRedirectMismatch": {
        "environment": "production-app-2025.06.14",
        "descriptions": [
            "users receive redirect_uri_mismatch during SSO login after frontend domain cutover",
            "OAuth callback fails because the staging callback URL was promoted to production settings",
            "Google login returns redirect mismatch after ingress host changed to app.example.com",
            "new regional login endpoint is rejected by identity provider due to missing callback registration",
            "authentication flow fails after trailing slash changed in the registered OAuth redirect URI",
            "OIDC login callback points to deprecated domain following DNS migration",
            "partner SSO starts failing because the release uses an unapproved redirect URL",
        ],
        "actions": [("register the exact production redirect URI", "success"), ("restart authentication service", "fail"), ("rollback frontend domain change", "success")],
    },
    "DBConnectionPoolExhaustion": {
        "environment": "production-db-15.6-app-2025.06.14",
        "descriptions": [
            "API requests time out because PostgreSQL connection pool is exhausted after traffic increase",
            "background workers wait for database connections after a slow query rollout",
            "checkout latency spikes while all application pool connections remain checked out",
            "reporting service cannot acquire a database connection during scheduled exports",
            "connection pool saturation follows a release that introduced an N+1 query path",
            "database clients queue indefinitely after transaction cleanup stopped returning connections",
            "inventory API shows pool timeout errors during flash sale load",
        ],
        "actions": [("increase pool capacity within database limits", "success"), ("restart application pods", "fail"), ("rollback slow query release", "success")],
    },
    "ImagePullBackOff": {
        "environment": "production-k8s-1.29.3",
        "descriptions": [
            "new API pods report ImagePullBackOff because the release image tag does not exist in registry",
            "deployment cannot pull private worker image after registry credentials were rotated",
            "CronJob remains pending with ImagePullBackOff following an incorrect image repository path",
            "web pods fail to pull image because the immutable digest was deleted from the registry",
            "canary deployment reports ErrImagePull after image tag was misspelled in Helm values",
            "cluster nodes cannot authenticate to container registry after service account secret change",
            "image pull fails for processor release because the image was never published by CI",
        ],
        "actions": [("publish or correct the image reference", "success"), ("restart affected pods", "fail"), ("restore registry pull credentials", "success")],
    },
}


def _id(*parts: str) -> str:
    return str(uuid.uuid5(SYNTHETIC_NAMESPACE, "|".join(parts)))


def seed_database() -> int:
    """Insert 35 deterministic synthetic incidents, attempts, and rolled-up stats.

    Re-running is safe: deterministic UUIDs make incident/attempt inserts idempotent.
    Existing non-synthetic records are never deleted or changed.
    """
    run_migration()
    records = []
    for signature, scenario in SCENARIOS.items():
        for index, description in enumerate(scenario["descriptions"]):
            records.append((signature, index, f"[SYNTHETIC] {description}", scenario))

    embeddings = embed_batch([record[2] for record in records])
    base_time = datetime.now(timezone.utc) - timedelta(days=21)
    for (signature, index, description, scenario), embedding in zip(records, embeddings, strict=True):
        incident_id = _id("incident", signature, str(index))
        created_at = base_time + timedelta(days=index * 2)
        query(
            """
            INSERT INTO incidents (id, signature, description, embedding, environment, created_at)
            VALUES (%s, %s, %s, %s::VECTOR, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (incident_id, signature, description, json.dumps(embedding, separators=(",", ",")), scenario["environment"], created_at),
        )
        for action_index, (action, result) in enumerate(scenario["actions"]):
            # A few historical variations give every action an interpretable record.
            if (
                signature == "CrashLoopBackOff"
                and action == "restore missing configuration key"
                and index in (1, 4)
            ):
                varied_result = "fail"
            elif action_index == 1 and index in (2, 6):
                varied_result = "success"
            else:
                varied_result = result
            query(
                """
                INSERT INTO attempts (id, incident_id, action, result, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    result = excluded.result,
                    created_at = excluded.created_at
                """,
                (_id("attempt", signature, str(index), str(action_index)), incident_id, action, varied_result, created_at + timedelta(hours=1)),
            )

    # Roll up only our synthetic records, preserving unrelated fix-stat history.
    query(
        """
        INSERT INTO fix_stats (signature, action, success_count, fail_count, last_success_at, last_env_version)
        SELECT i.signature, a.action,
               count(*) FILTER (WHERE a.result = 'success'),
               count(*) FILTER (WHERE a.result = 'fail'),
               max(a.created_at) FILTER (WHERE a.result = 'success'),
               max(i.environment)
        FROM incidents AS i
        JOIN attempts AS a ON a.incident_id = i.id
        WHERE i.description LIKE '[SYNTHETIC]%%'
        GROUP BY i.signature, a.action
        ON CONFLICT (signature, action) DO UPDATE SET
            success_count = excluded.success_count,
            fail_count = excluded.fail_count,
            last_success_at = excluded.last_success_at,
            last_env_version = excluded.last_env_version
        """
    )
    return len(records)


if __name__ == "__main__":
    print(f"Loaded {seed_database()} synthetic incidents.")
