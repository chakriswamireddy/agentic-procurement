# Agentic Procurement

A local-first reference implementation of an agentic procurement platform. Phase 0
builds the reproducible data foundation: four local stores, a deterministic synthetic
dataset, synthetic policy documents, and a rebuildable Qdrant policy index. Phase 1
adds the FastAPI service with settings, logging, correlation IDs, error handling,
async PostgreSQL access, supplier read APIs, and health checks. Phase 2 adds the policy
document registry, section-aware chunking, dense and sparse embeddings, idempotent
indexing, metadata filters, hybrid retrieval, evidence objects, calibrated abstention,
untrusted-evidence handling, document and policy APIs, and a retrieval evaluation set.
Phase 3 adds the LangGraph workflow: typed state, parallel supplier/policy research,
deterministic comparison and scoring, validation routing, a Postgres checkpointer, an
approval interrupt with resume, an execution gateway, and the request/workflow APIs.

Phases 4–7 (orchestration, MCP/auth/approval, production evaluation, and the
frontend) are not implemented yet.

## What Phase 0 provides

- PostgreSQL for supplier identity, products, quotations, requests, recommendations,
  approvals, execution records, and audit events.
- MongoDB for flexible supplier profile extensions and raw external ERP payloads.
- Redis for disposable cache and coordination data.
- Qdrant for the derived policy-chunk retrieval index.
- A deterministic seed generator with documented edge cases.
- Idempotent seeders, minimal policy ingestion, a connectivity checker, and a
  destructive reset command.

## What Phase 2 provides

- A PostgreSQL `policy_documents` registry with versioned rows, checksums, chunk counts,
  and ingestion status.
- Front-matter validation and section-aware, token-bounded chunking with deterministic
  UUIDv5 chunk IDs.
- FastEmbed dense (`BAAI/bge-small-en-v1.5`) and sparse (`Qdrant/bm25`) providers behind
  async interfaces with batching and timeouts.
- A reproducible Qdrant collection with named `dense` and `sparse` vectors and payload
  indexes.
- Idempotent indexing that upserts new points, deletes stale points when a document
  shrinks, and records failures in the registry.
- Qdrant-side filters for status, classification, effective dates, and document IDs.
- Dense, sparse, and hybrid retrieval with reciprocal rank fusion and debug ranks.
- Evidence objects built only from Qdrant payloads, with citation validation and
  repository-relative source paths.
- Abstention when no evidence survives filters or both raw relevance signals are weak;
  thresholds are documented in `docs/decisions/0005-retrieval-threshold.md`.
- Injection-suspected chunks are marked and delimited as untrusted data; the grounded
  prompt forbids following evidence instructions and forbids model approval.
- Document upload/list/detail/ingest endpoints and an evidence-returning policy search
  endpoint.
- A 20-case evaluation set and `scripts/evaluate_retrieval.py`, which compares dense,
  sparse, and hybrid retrieval on recall, MRR, context precision, abstention accuracy,
  and version-leak rate.

## What Phase 3 provides

- A typed `ProcurementState` whose only reducer is the additive `errors` list; every
  other key has a single writer, and all values stay JSON-serializable for the
  checkpointer.
- A compiled LangGraph `StateGraph`: request validation fans out into parallel
  supplier and policy research, merges at a join node, then runs deterministic
  comparison, validation, an approval interrupt, execution, and a terminal record step.
- Deterministic eligibility (ten reason codes) and versioned scoring
  (`SCORING_VERSION = "1.0"`, weights 0.55/0.30/0.15) in pure Python — the LLM never
  decides ranking or approval.
- Recommendation validation that recomputes the score, checks constraints, and audits
  evidence fields and statuses with machine-readable issue codes.
- An `AsyncPostgresSaver` checkpointer with its own connection string
  (`CHECKPOINTER_DATABASE_URL`), so a paused workflow survives process restarts.
- An approval `interrupt()` with a secret-free payload; approve, reject, and invalid
  resume paths; a `FakeExecutionGateway` behind a stable protocol with idempotency key
  `<request_id>:<version>`.
- A workflow service that merges graph state with PostgreSQL business rows, plus
  request and workflow APIs (resume is development-only until Phase 5).

Graph diagram: `docs/architecture/graph.mmd`.

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker Engine with Docker Compose v2
- Ports `5432`, `27017`, `6379`, `6333`, and `6334` free on localhost

## Quick start

```bash
cd agentic-procurement
cp .env.example .env

# Replace the placeholder JWT secret in .env. Do not commit .env.
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

make up
make seed
make check
make api
```

If the Qdrant volume was created by Phase 0, rebuild the collection once for the named
`dense`/`sparse` vector schema:

```bash
uv run python scripts/ingest_documents.py --rebuild --yes
```

The API runs at `http://localhost:8000` with interactive docs at
`http://localhost:8000/docs`.

Expected final output from `make check`:

```text
postgres: ok (100 suppliers)
mongodb: ok (100 profiles)
redis: ok (pong)
qdrant: ok (1 collections)
```

## Commands

| Command | Purpose |
|---|---|
| `make up` | Start PostgreSQL, MongoDB, Redis, and Qdrant |
| `make down` | Stop the containers; named volumes are preserved |
| `make seed` | Generate data, seed PostgreSQL and MongoDB, ingest policy documents |
| `make check` | Verify connectivity and print store counts |
| `make api` | Run the FastAPI service on port 8000 with reload |
| `make logs` | Follow container logs |
| `make reset` | Delete all local store data and rebuild everything from source |
| `make test` | Run ruff and the full test suite |
| `make eval` | Evaluate dense, sparse, and hybrid retrieval on the 20-case set |

`make reset` is destructive. It runs `scripts/reset_environment.sh --yes`, which
removes the named Docker volumes before rebuilding.

## Phase 2 API endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/documents` | Upload a Markdown policy (multipart `file`) |
| `GET` | `/api/v1/documents` | List registry records, optional `status` |
| `GET` | `/api/v1/documents/{id}` | Read one version, optional `version` |
| `POST` | `/api/v1/documents/{id}/ingest` | Load and index a registered document |
| `GET` | `/api/v1/policies/search` | Retrieve evidence for `q` (3–500 chars) |

Search supports `limit` (1–20), `as_of`, repeated `classification`, and repeated
`document_ids` query parameters. Abstention is a `200` response with
`inconclusive: true` and an empty `evidence` list; an unavailable Qdrant or embedding
provider returns `503 dependency_unavailable`.

## Phase 3 workflow endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/procurement/requests` | Create a request and run the workflow until approval or a terminal state (`201` + `X-Workflow-Status`) |
| `GET` | `/api/v1/procurement/requests/{id}` | Read the request with its recommendation summary |
| `GET` | `/api/v1/workflows/{thread_id}` | Workflow status, current node, recommendation, evidence IDs |
| `POST` | `/api/v1/workflows/{thread_id}/approval` | Resume with `approved`/`rejected`; development-only until Phase 5 (`403` otherwise) |

Request creation and graph start are combined: a new request returns `201` with the
paused workflow state rather than a bare `202`. Repeating an approval after a terminal
status returns `409`.

## Repository layout

```text
agentic-procurement/
├── backend/
│   ├── app/                  # FastAPI application
│   │   ├── api/              # Routes and dependency providers
│   │   ├── core/             # Settings, logging, errors, middleware
│   │   ├── database/         # Async PostgreSQL and MongoDB access
│   │   ├── graph/            # State, nodes, routing, checkpointer (Phase 3)
│   │   ├── rag/              # Loader, chunker, embeddings, indexer, retriever, fusion
│   │   ├── repositories/     # SQL and Mongo data access
│   │   ├── schemas/          # Pydantic API contracts
│   │   └── services/         # Business logic
│   └── tests/                # Unit, graph, dataset, and integration tests
├── data/
│   ├── documents/            # Synthetic policy Markdown with YAML front matter
│   ├── evaluation/           # Empty until Phase 6
│   └── seed/                 # Deterministic generated fixtures
├── docs/
│   ├── architecture/         # Graph diagram (graph.mmd)
│   ├── decisions/            # ADRs for dataset design and data ownership
│   ├── learning-log/         # Phase notes, drills, and checkpoint answers
│   └── phases/               # Phase-specific notes
├── frontend/                 # Reserved for Phase 7
├── infrastructure/
│   └── docker-compose.yml    # Local PostgreSQL, MongoDB, Redis, Qdrant
├── scripts/
│   ├── sql/001_schema.sql    # Canonical Phase 0 schema
│   ├── sql/002_documents.sql # Policy document registry
│   ├── generate_dataset.py   # Deterministic fixture generator
│   ├── seed_postgres.py      # Idempotent PostgreSQL seeder
│   ├── seed_mongodb.py       # Idempotent MongoDB seeder
│   ├── ingest_documents.py   # Minimal Qdrant ingestion pipeline
│   ├── check_connectivity.py # Store diagnostic
│   └── reset_environment.sh  # Destructive rebuild
├── Makefile
└── pyproject.toml
```

## Dataset

| File | Records |
|---|---:|
| `data/seed/suppliers.json` | 100 |
| `data/seed/products.json` | 200 |
| `data/seed/quotations.json` | 500 |
| `data/seed/users.json` | 15 |
| `data/seed/purchase_requests.json` | 100 |
| `data/seed/purchase_orders.json` | 150 |
| `data/seed/supplier_profiles.jsonl` | 100 |
| `data/seed/raw_supplier_payloads.jsonl` | 60 |

The generator uses a fixed seed and fixed reference date (`2026-01-01`). Verify that
the checked-in fixtures match the generator:

```bash
uv run python scripts/generate_dataset.py --check
```

Deliberate edge cases are documented in `docs/decisions/0001-dataset-design.md`:
expired quotations, insufficient quantities, long deliveries, missing certifications,
inactive or suspended suppliers, duplicate-looking names, and one anomalous price.

## Policy documents and retrieval

`data/documents/` contains 12 synthetic policy files. They include active policies,
one obsolete version (`POL-011`), one draft conflict (`POL-012`), laptop-related
passages, a near-miss accessories passage, and a prompt-injection fixture. Fixture
locations are recorded in `docs/decisions/0003-policy-fixture-notes.md`.

Ingestion validates YAML front matter, records metadata in PostgreSQL, and chunks by
Markdown section with a 350-token target and 50-token overlap. Chunks carry a short
`[Section: ...]` prefix and are embedded both densely (`BAAI/bge-small-en-v1.5`, 384
dimensions by default) and sparsely (`Qdrant/bm25`). The `policy_chunks` collection
stores named `dense` and `sparse` vectors in one point with deterministic UUIDv5 point
IDs, so rerunning ingestion does not duplicate points.

Retrieval supports dense-only, sparse-only, and hybrid modes. Hybrid mode fuses the two
ranked lists with reciprocal rank fusion (`k=60`) and preserves both source ranks.
Filters for status, classification, effective dates, and document IDs are applied inside
Qdrant. See `docs/decisions/0004-rag-indexing-decisions.md` for chunking, collection,
and re-indexing decisions.

The first sparse-model use downloads `Qdrant/bm25` into the FastEmbed cache. Set
`FASTEMBED_CACHE_DIR` to pin the cache location.

## Data ownership

See `docs/decisions/0002-data-ownership.md` for the full table. The short version:

- PostgreSQL is authoritative for business records and the policy document registry.
- MongoDB owns profile extensions and raw payloads only.
- Redis is disposable cache.
- Qdrant is a derived index rebuilt from `data/documents/`.

## Tests

```bash
uv run ruff check .
uv run pytest -q
```

Unit tests do not require Docker. Integration tests are marked `integration` and use
the URLs in `.env`; start the stack first with `make up && make seed`.

The Phase 2 tests cover loader validation, section-aware chunking, overlap bounds,
deterministic chunk IDs, RRF order, filter construction, idempotent indexing, stale-point
deletion after a document shrinks, obsolete/draft exclusion, effective-date boundaries,
exact-term versus paraphrase retrieval, evidence and citation validation, abstention,
injection marking, document upload rules, and the document/policy API contracts.

The Phase 3 tests (`backend/tests/graph/` plus unit suites) cover eligibility reason
codes, scoring determinism and tie-breaks, every validation issue code, every routing
branch, parallel error merging, the recursion limit, the approval interrupt and all
three resume outcomes, checkpoint persistence across graph instances (in-memory and
Postgres), and the end-to-end request → pause → approve/reject → terminal API flow.

Retrieval quality and abstention calibration:

```bash
make eval
```

The script prints per-case results and writes a JSON summary under
`data/evaluation/retrieval_results_<timestamp>.json` (gitignored). It exits non-zero if
any obsolete or draft result leaks or hybrid recall@5 falls below `0.8`. Thresholds are
documented in `docs/decisions/0005-retrieval-threshold.md`.

## Persistence

Named volumes preserve data across `docker compose restart` and `docker compose down`
followed by `make up`. Only `docker compose down -v` or `make reset` removes store
data. Recorded verification results are in `docs/learning-log/phase-0.md`.
