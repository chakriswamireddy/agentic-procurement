# ADR 0004: RAG indexing, chunking, and retrieval decisions

- **Status:** Accepted
- **Date:** 2026-11-02
- **Phase:** 2 (steps 2.1–2.8)
- **Decision owner:** Policy RAG pipeline

## Context

Phase 0 built a naive paragraph index with an unnamed dense vector. Phase 2 replaces
it with a section-aware, versioned, hybrid-retrieval pipeline. The pipeline must keep
PostgreSQL and `data/documents/` authoritative while treating Qdrant as a derived,
rebuildable index.

Phase 2 needs explicit decisions for the registry key, chunking, collection schema,
and re-indexing behaviour so implementation and tests agree.

## Decisions

### 1. Registry key is `(id, version)`

`policy_documents` uses a composite primary key on `(id, version)`. The Phase 2 guide's
sketch shows `id TEXT PRIMARY KEY` and `UNIQUE (id, version)` together, but that would
prevent multiple versions of the same document. The stated requirement is that a
document can have multiple versions, so the composite key is the effective unique
constraint. `id` remains the business `document_id` such as `POL-001`.

### 2. Dense and sparse vectors share one Qdrant point

The `policy_chunks` collection defines two named vectors:

- `dense`: `EMBEDDING_DIM` (384 by default), cosine distance
- `sparse`: BM25 sparse vector from `Qdrant/bm25`

Keeping both vectors on one point lets dense, sparse, and hybrid queries share the
same payload and filters. The collection is created from code, never only from the
dashboard. An existing Phase 0 collection with an unnamed vector must be rebuilt with
`scripts/ingest_documents.py --recreate`.

### 3. Section-aware, token-bounded chunks with a section prefix

Chunks follow Markdown heading hierarchy. `section_path` records the hierarchy
(for example `Procurement Policy > 4. Approval thresholds > 4.3 Laptop purchases`).
Embedded text is prefixed with `[Section: ...]` so the model sees heading context;
the same path is stored in metadata for citations.

Defaults are `target_tokens=350` and `overlap_tokens=50`, with overlap capped at 20% of
the target. `bge-small-en-v1.5` has a 512-token limit, so 350 leaves headroom.
Token counts use `tiktoken`'s `cl100k_base` encoding as a documented approximation:
the embedding model uses a different tokenizer, and the headroom absorbs the
difference.

Chunk IDs are UUIDv5 values over document, version, section path, chunk index, and a
SHA-256 of the chunk text.

### 4. Re-indexing is two-phase: upsert new points, then delete stale points

`PolicyIndexer.index_document` first upserts every new point, then deletes point IDs
that existed for `(document_id, version)` but are not in the new set. This handles
documents that shrink without leaving a window in which the document has no index at
all.

The remaining failure window is between the upsert and the stale-point deletion. If the
process dies there, the registry cannot report success because the in-process exception
handler did not run; a later run repairs the state because point IDs are deterministic
and stale IDs are recomputed. Point-count verification after the delete catches count
mismatches and marks the registry row `failed`. A versioned collection or alias swap is
the stronger future design; it is not required for the local MVP.

On any handled failure, the registry row is marked `failed` with a short error message.
It is never marked `ingested` before the Qdrant upsert and count check succeed.

### 5. Metadata filters run inside Qdrant

Status, classification, document ID, and effective-date filters are part of the Qdrant
query. Post-filtering is not used because it can starve top-k and lets filtered content
influence ranking. Effective dates are stored as UTC-midnight RFC 3339 timestamps so
Qdrant datetime ranges behave predictably. An absent `effective_to` is stored as JSON
null and matched with `IsNullCondition`.

### 6. RRF uses ranks only

Hybrid retrieval fuses dense and sparse results with reciprocal rank fusion,
`sum(1 / (k + rank))` with `k = 60`. Raw cosine and BM25 scores are never added
because they are not comparable. Ties break on `chunk_id` for deterministic output.
Both source ranks are retained for debugging.

## Consequences

- The policy registry is authoritative for document metadata and ingestion status;
  Qdrant remains fully rebuildable from `data/documents/`.
- Changing the embedding model or dimension requires `--recreate`; the indexer fails
  loudly on a dimension or missing-sparse-vector mismatch.
- The first sparse-model use downloads `Qdrant/bm25` into the FastEmbed cache. Set
  `FASTEMBED_CACHE_DIR` to pin the cache location.
- Chunk counts and IDs are stable only while the chunker configuration and document
  content are stable. Changing `target_tokens` or `overlap_tokens` requires a rebuild.
