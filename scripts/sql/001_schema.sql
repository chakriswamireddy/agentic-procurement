BEGIN;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'requester', 'approver', 'auditor')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS suppliers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    location TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'inactive', 'suspended')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_suppliers_status_category
    ON suppliers (status, category);

CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    attributes_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_products_category
    ON products (category);

CREATE TABLE IF NOT EXISTS quotations (
    id TEXT PRIMARY KEY,
    supplier_id TEXT NOT NULL REFERENCES suppliers (id) ON DELETE RESTRICT,
    product_id TEXT NOT NULL REFERENCES products (id) ON DELETE RESTRICT,
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    currency TEXT NOT NULL DEFAULT 'INR',
    available_quantity INTEGER NOT NULL CHECK (available_quantity >= 0),
    delivery_days INTEGER NOT NULL CHECK (delivery_days >= 0),
    valid_until DATE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quotations_supplier_product
    ON quotations (supplier_id, product_id);

CREATE TABLE IF NOT EXISTS procurement_requests (
    id TEXT PRIMARY KEY,
    requester_id TEXT NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    product_id TEXT NOT NULL REFERENCES products (id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    constraints_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'submitted',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_procurement_requests_requester_created
    ON procurement_requests (requester_id, created_at);

CREATE TABLE IF NOT EXISTS recommendations (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES procurement_requests (id) ON DELETE RESTRICT,
    supplier_id TEXT NOT NULL REFERENCES suppliers (id) ON DELETE RESTRICT,
    score NUMERIC(6, 2) NOT NULL,
    rationale_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    version INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (request_id, version)
);

CREATE TABLE IF NOT EXISTS approval_decisions (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES procurement_requests (id) ON DELETE RESTRICT,
    approver_id TEXT NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    reason TEXT,
    recommendation_version INTEGER NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (request_id, recommendation_version)
);

CREATE TABLE IF NOT EXISTS execution_records (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE REFERENCES procurement_requests (id) ON DELETE RESTRICT,
    idempotency_key TEXT NOT NULL UNIQUE,
    external_reference TEXT,
    status TEXT NOT NULL,
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    actor_id TEXT REFERENCES users (id) ON DELETE RESTRICT,
    request_id TEXT REFERENCES procurement_requests (id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL,
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    correlation_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_events_request_created
    ON audit_events (request_id, created_at);

CREATE INDEX IF NOT EXISTS idx_audit_events_correlation_id
    ON audit_events (correlation_id);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id TEXT PRIMARY KEY,
    supplier_id TEXT NOT NULL REFERENCES suppliers (id) ON DELETE RESTRICT,
    product_id TEXT NOT NULL REFERENCES products (id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_purchase_orders_supplier_created
    ON purchase_orders (supplier_id, created_at);

COMMENT ON COLUMN products.attributes_json IS
    'Flexible product attributes; PostgreSQL remains the system of record for product identity.';

COMMENT ON COLUMN quotations.valid_until IS
    'Last date on which the quotation may be used for a new recommendation.';

COMMENT ON COLUMN procurement_requests.constraints_json IS
    'Request-specific constraints such as maximum delivery days and required certifications.';

COMMENT ON COLUMN recommendations.score IS
    'Bounded deterministic comparison score for the recommendation version.';

COMMENT ON COLUMN recommendations.rationale_json IS
    'Structured explanation supporting the recommendation.';

COMMENT ON COLUMN recommendations.evidence_json IS
    'Structured references to supplier, quotation, and policy evidence.';

COMMENT ON COLUMN recommendations.version IS
    'Monotonically increasing recommendation version per request.';

COMMENT ON COLUMN approval_decisions.recommendation_version IS
    'Recommendation version that the approver decided on.';

COMMENT ON COLUMN execution_records.idempotency_key IS
    'Caller-supplied key preventing duplicate external execution.';

COMMENT ON COLUMN execution_records.external_reference IS
    'Identifier returned by the simulated external procurement system.';

COMMENT ON COLUMN audit_events.correlation_id IS
    'Request or workflow correlation identifier used to trace an operation.';

COMMENT ON TABLE purchase_orders IS
    'PostgreSQL-owned minimal purchase order table added for the demo dataset.';

COMMIT;
