BEGIN;

CREATE TABLE IF NOT EXISTS policy_documents (
    id TEXT NOT NULL,
    version TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'obsolete', 'draft')),
    classification TEXT NOT NULL CHECK (classification IN ('public', 'internal', 'restricted')),
    effective_from DATE NOT NULL,
    effective_to DATE,
    source_path TEXT NOT NULL,
    checksum TEXT NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    ingestion_status TEXT NOT NULL DEFAULT 'registered'
        CHECK (ingestion_status IN ('registered', 'ingesting', 'ingested', 'failed')),
    ingestion_error TEXT,
    ingested_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, version),
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE INDEX IF NOT EXISTS idx_policy_documents_status
    ON policy_documents (status);

CREATE INDEX IF NOT EXISTS idx_policy_documents_ingestion_status
    ON policy_documents (ingestion_status);

COMMENT ON TABLE policy_documents IS
    'Registry of policy source files. PostgreSQL owns metadata and ingestion status; '
    'Qdrant is the derived chunk index; data/documents remains the content source.';

COMMENT ON COLUMN policy_documents.id IS
    'Business document identifier such as POL-001. A document may have multiple versions.';

COMMENT ON COLUMN policy_documents.version IS
    'Document version string from YAML front matter; (id, version) is the registry key.';

COMMENT ON COLUMN policy_documents.checksum IS
    'SHA-256 of the raw Markdown file, used to detect content drift.';

COMMENT ON COLUMN policy_documents.ingestion_status IS
    'registered -> ingesting -> ingested | failed. Never mark ingested before Qdrant upsert succeeds.';

COMMIT;
