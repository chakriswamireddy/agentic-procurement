# Phase 2 learning log — Policy RAG ingestion and retrieval

- **Date:** 2026-11-02, completed 2026-11-04
- **Scope completed:** Steps 2.1–2.14 (registry, loader, chunker, embeddings, collection, indexer, filters, retrieval, evidence, abstention, APIs, ingestion flags, evaluation set and script)

## My explanation

Phase 0 indexed paragraphs by character count. Phase 2 makes evidence citable: documents
are registered in PostgreSQL, validated from YAML front matter, split on heading
boundaries, embedded densely and sparsely, and stored in one Qdrant point with filters
for status, classification, effective dates, and document ID. Retrieval can run dense
only, sparse only, or hybrid, where reciprocal rank fusion combines ranks without
comparing incomparable scores.

## Architecture and execution flow

```text
data/documents/*.md
        |
        +--> document_loader.py  (validate front matter, checksum, relative path)
        |          |
        |          +--> policy_documents (PostgreSQL registry)
        |          |
        |          +--> chunker.py (section-aware, 350 tokens, 50 overlap)
        |                     |
        |                     +--> embeddings.py (dense bge-small + sparse bm25)
        |                                |
        |                                +--> indexer.py
        |                                       (named vectors, upsert, stale-point delete)
        |                                                |
        |                                                +--> Qdrant policy_chunks
        |
        +--> retriever.py (dense / sparse / hybrid + Qdrant-side filters)
                     |
                     +--> fusion.py (RRF, k=60, dense/sparse ranks preserved)
```

## What I implemented

- `policy_documents` registry with a composite `(id, version)` key, checksum, chunk
  count, and `registered -> ingesting -> ingested | failed` ingestion status.
- Loader validation for extension, 2 MB size limit, YAML front matter, status,
  classification, document ID format, effective-date ordering, and checksum.
- Section-aware chunker using heading hierarchy, sentence accumulation, bounded
  overlap, deterministic UUIDv5 chunk IDs, and hard-split recording.
- Dense FastEmbed provider and sparse BM25 provider behind async interfaces, with
  batching, timeouts, dimension checks, and model-instance caching.
- Reproducible Qdrant collection with named `dense` and `sparse` vectors, payload
  indexes, deterministic point IDs, and clear dimension-mismatch errors.
- Two-phase indexer: upsert new points, delete stale points, verify count, and update
  the registry only after success.
- Filters for status, classification, effective-date boundaries, and document IDs,
  applied inside Qdrant.
- Dense, sparse, and hybrid retrieval with RRF, preserved debug ranks, and deterministic
  tie-breaking.
- Ingestion script rewired to the application pipeline, including registry schema
  application for standalone runs.
- Evidence objects derived only from retrieved payloads, with citation validation and
  host-path sanitisation.
- Abstention using raw dense and sparse scores because RRF scores have a fixed floor;
  thresholds calibrated in ADR 0005.
- Untrusted-evidence handling: injection patterns mark chunks, evidence is serialised as
  data in prompts, and the system prompt forbids following evidence instructions or
  approving requests.
- Document upload/list/detail/ingest APIs and the policy search API.
- Ingestion flags `--all`, `--document-id`, `--version`, `--dry-run`, `--rebuild`, and
  `--yes`, with a per-document result table and non-zero exit on failures.
- A 20-case manually verified retrieval set and an evaluation script reporting recall,
  MRR, context precision, abstention accuracy, and version-leak rate for dense, sparse,
  and hybrid modes.

## Verification

```text
uv run ruff check .
All checks passed!

uv run pytest -q -m 'not integration'
93 passed, 27 deselected

uv run pytest -q -m integration
27 passed, 93 deselected

uv run python scripts/ingest_documents.py --all --dry-run
12 documents validated and chunked; 226 chunks total

uv run python scripts/evaluate_retrieval.py
hybrid recall@5 1.000, MRR@5 0.883, version leak rate 0.000
```

The evaluation comparison:

| Mode | Recall@5 | MRR@5 | Context precision@5 | Abstention accuracy | False abstention | Version leaks |
|---|---:|---:|---:|---:|---:|---:|
| dense | 0.944 | 0.810 | 0.356 | 1.000 | 0.000 | 0.000 |
| sparse | 0.944 | 0.944 | 0.311 | 1.000 | 0.000 | 0.000 |
| hybrid | 1.000 | 0.883 | 0.322 | 1.000 | 0.000 | 0.000 |

Full policy re-ingestion after replacing the Phase 0 collection:

```text
POL-001 v3.2: 25 chunks      POL-007 v2.1: 17 chunks
POL-002 v4.1: 20 chunks      POL-008 v1.9: 19 chunks
POL-003 v2.3: 19 chunks      POL-009 v1.5: 18 chunks
POL-004 v1.8: 19 chunks      POL-010 v1.2: 20 chunks
POL-005 v1.4: 22 chunks      POL-011 v2.0: 14 chunks (obsolete)
POL-006 v2.0: 19 chunks      POL-012 v0.9: 14 chunks (draft)
ingested 12 documents into policy_chunks (226 chunks)
```

Manual retrieval for `approval threshold for laptop purchases`:

```text
dense  : POL-001 section 4.3, POL-001 section 4.3, POL-008 section 5.1
sparse : POL-001 section 4.1, POL-001 section 4.3, POL-001 section 4.3
hybrid : POL-001 section 4.3 (dense rank 1, sparse rank 2), ...
```

Default filters returned no `POL-011`; an explicit `as_of=2025-06-01` query with
obsolete statuses allowed returned `POL-011`, confirming version and date filters work
inside Qdrant.

## Failure drills

| # | Drill | Observed behaviour |
|---|---|---|
| 1 | Embedding provider down | `IndexingError`/`EmbeddingError` marks the registry row `failed` with a safe message; Qdrant points are not left claiming success |
| 2 | Qdrant down | Policy search maps the client failure to `503 dependency_unavailable`; readiness reports Qdrant down |
| 3 | Dimension mismatch | `ensure_collection` raised `IndexSchemaError` instead of silently returning empty results |
| 4 | Malformed front matter during a full run | Loader rejects that file with file and field; the ingestion script continues and exits non-zero with a failure summary |
| 5 | Duplicate `(document_id, version)` with different content | Loader/upload rejects the second file because the checksum differs |
| 6 | Document shrinks | Integration test re-indexed a shorter document and confirmed old point IDs were deleted |
| 7 | Obsolete or draft version | Default queries exclude both; explicit status filters return them |
| 8 | Exact term versus paraphrase | `ISO14001` is retrieved by sparse/exact matching; a paraphrased certification question returns the expected active document |
| 9 | No evidence | Off-domain queries return `inconclusive: true`, `reason: weak_evidence`, with an empty evidence list |
| 10 | Injection document | The chunk is retrievable, marked `injection_suspected: true`, and the prompt wrapper treats it as data rather than instructions |
| 11 | Huge query | API validation rejects a query over 500 characters with `422` |

Abstention was calibrated on real scores: off-domain top dense scores were at most
`0.54`, relevant scores at least `0.63`; off-domain sparse scores were absent or at most
`1.59`, relevant sparse scores at least `3.5` except exact identifiers. See ADR 0005.

## Trade-offs

- `tiktoken` is an approximation of the bge tokenizer. The 350-token target leaves
  enough headroom below 512 that the approximation is safe in practice.
- Two-phase indexing avoids an empty-index window but can leave stale points if the
  process dies before deletion. Deterministic IDs and a re-run repair it.
- The registry uses a composite key rather than the guide's literal single-column
  primary key so that multiple versions are actually possible. This is documented in
  ADR 0004.
- RRF is implemented locally rather than using Qdrant's built-in fusion so ranks remain
  explicit and testable without a live server.
- Hybrid retrieval has no reranker yet. Reranking remains an optional stretch after
  measuring the eval set; hybrid already reaches recall@5 `1.000`.
- Abstention uses preserved raw dense/sparse scores because RRF has a fixed score floor.
  This adds two diagnostics fields to each fused hit but keeps fusion rank-only.
- Citation validation rejects any chunk that was not in the current retrieval result,
  even if it exists in Qdrant. This is stricter than index membership and prevents an
  answer from citing evidence the caller did not receive.

## Checkpoint answers

1. **Why section-aware chunking?** Policy answers are clause-scoped. Section boundaries
   keep a threshold, its exception, and its approver together and give citations a
   stable `section_path`; fixed windows can split a list away from its heading.
2. **Chunk size trade-off?** Smaller chunks raise precision and citation focus but lose
   context and can split conditions; larger chunks preserve context but dilute the
   embedding and waste generation tokens. The 350-token target leaves headroom under the
   model's 512-token limit.
3. **Why dense and sparse?** Dense handles paraphrase ("certification needed to
   onboard"); sparse handles exact identifiers (`ISO14001`, `500`). Each fails where the
   other succeeds.
4. **Why RRF uses ranks?** Cosine and BM25 scores have different scales and
   distributions. Ranks are comparable; summing raw scores would let one retriever
   dominate arbitrarily.
5. **Why filter inside Qdrant?** Post-filtering top-k lets obsolete or unauthorized
   content consume candidate slots and influence ranking before being removed.
6. **How are obsolete versions prevented from influencing recommendations?** Default
   filters require `status=active`; `as_of` adds effective-date bounds; the evaluation
   reports a version-leak rate that must remain `0`.
7. **Why is ingestion idempotent, and what about shrinking documents?** Deterministic
   UUIDv5 point IDs plus upsert make reruns stable; the indexer compares existing point
   IDs with the new set and deletes stale ones when a document shrinks.
8. **What is the source of truth?** `data/documents/` holds policy text; PostgreSQL holds
   the registry and status; Qdrant is derived and rebuildable with
   `ingest_documents.py --rebuild --yes`.
9. **When should the system abstain, and how was it calibrated?** When no hit survives
   filters, when both raw relevance signals are below the calibrated thresholds, or when
   all text is too short. Thresholds came from measured relevant versus off-domain
   scores, not guesses.
10. **How is instructions-in-documents handled?** Retrieved text is serialised as data
    with `injection_suspected` metadata; the system prompt explicitly forbids following
    it or approving anything.
11. **Which metric reveals many irrelevant chunks?** Context precision at k; recall can
    still be high while precision is low.
12. **How to evaluate a reranker separately?** Reuse the same retrieval eval set and
    compare recall, MRR, and context precision before and after reranking, with
    generation held constant or excluded entirely.

## Checkpoint score

**Self-assessed score: 87/100**

| Dimension | Score | Notes |
|---|---:|---|
| Conceptual understanding | 18/20 | Retrieval, fusion, and abstention trade-offs are clear; reranking is untested |
| Architecture and data flow | 14/15 | Registry, index, APIs, and rebuild paths are explicit |
| Independent implementation | 22/25 | Full Phase 2 path works; upload/ingest API lacks a dedicated integration test |
| Debugging and trade-offs | 17/20 | Drills reproduced; embedding-provider outage drill is reasoned rather than re-run |
| Interview explanation | 16/20 | Answers are complete; performance and reranking depth need more practice |

This is above the Phase 2 threshold of 75.
