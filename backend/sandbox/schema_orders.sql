-- Phase 2 sandbox-only orders data. This is separate from RecallOps memory tables.
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item STRING NOT NULL,
    qty INT8 NOT NULL CHECK (qty > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Stable IDs make this tiny synthetic seed idempotent.
INSERT INTO orders (id, item, qty) VALUES
    ('10000000-0000-0000-0000-000000000001', 'wireless keyboard', 2),
    ('10000000-0000-0000-0000-000000000002', 'USB-C dock', 1),
    ('10000000-0000-0000-0000-000000000003', 'monitor arm', 3),
    ('10000000-0000-0000-0000-000000000004', 'laptop stand', 1),
    ('10000000-0000-0000-0000-000000000005', 'webcam', 4)
ON CONFLICT (id) DO NOTHING;
