-- RecallOps Phase 1 schema.
--
-- EXACT CockroachDB vector syntax used below (VERIFY against the target cluster):
--   embedding VECTOR(768)
--   CREATE VECTOR INDEX IF NOT EXISTS incidents_embedding_vector_idx
--       ON incidents (embedding);
-- CockroachDB documents `CREATE VECTOR INDEX ... (vector_column)` and L2 `<->`
-- searches. On older preview clusters, vector indexing may need
-- `SET CLUSTER SETTING feature.vector_index.enabled = true` (requires admin),
-- and some versions accept `USING cspann (embedding)` / `USING hnsw (embedding)`
-- instead. Do not issue that cluster setting from this application.

CREATE TABLE IF NOT EXISTS incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signature STRING NOT NULL,
    description STRING NOT NULL,
    embedding VECTOR(768) NOT NULL,
    environment STRING NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id),
    action STRING NOT NULL,
    result STRING NOT NULL CHECK (result IN ('success', 'fail')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fix_stats (
    signature STRING NOT NULL,
    action STRING NOT NULL,
    success_count INT8 NOT NULL DEFAULT 0,
    fail_count INT8 NOT NULL DEFAULT 0,
    last_success_at TIMESTAMPTZ,
    last_env_version STRING,
    PRIMARY KEY (signature, action)
);

CREATE TABLE IF NOT EXISTS playbooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signature STRING NOT NULL,
    action STRING NOT NULL,
    rationale STRING NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor STRING NOT NULL,
    action STRING NOT NULL,
    target STRING NOT NULL,
    outcome STRING NOT NULL
);

CREATE INDEX IF NOT EXISTS attempts_incident_id_idx ON attempts (incident_id);
CREATE INDEX IF NOT EXISTS incidents_signature_idx ON incidents (signature);
CREATE VECTOR INDEX IF NOT EXISTS incidents_embedding_vector_idx ON incidents (embedding);
