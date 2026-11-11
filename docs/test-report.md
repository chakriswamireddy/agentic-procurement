# Test & Evaluation Report: Agentic Procurement Platform

**System:** Agentic Procurement Reference Architecture  
**Verification Date:** November 2026  
**Environment:** Linux x86_64 / Docker Compose / Python 3.12 / React 18 + Vite  

---

## 1. Test Suite Summary & Execution Commands

| Test Suite | Framework / Tool | Command | Test Count | Pass Rate |
|---|---|---|---|---|
| **Backend Unit & Integration** | Pytest + pytest-asyncio | `uv run pytest -q` | 338 | 100% (338/338) |
| **Frontend Unit & Component** | Vitest + React Testing Library | `cd frontend && npm test` | 17 | 100% (17/17) |
| **Deterministic Eval Harness** | Custom Evaluation Framework | `uv run python scripts/run_evaluation.py` | 20 | 100% (20/20) |
| **Container Smoke Verification** | Bash + cURL + Docker Compose | `bash scripts/verify_stack.sh` | 1 | PASS |
| **Static Code Quality** | Ruff Linter & Formatter | `uv run ruff check .` | - | Clean |

---

## 2. Test Coverage by Architectural Layer

### Layer 1: Core Data & Specialized Storage
- **PostgreSQL Repositories:** Validates transactional CRUD, soft deletes, foreign keys, and optimistic concurrency locks.
- **MongoDB Client:** Tests dynamic document insertion for ISO certifications and compliance profiles; validates schema flexibility.
- **Qdrant Vector Store:** Verifies dense and sparse payload indexing, filter pruning, and hybrid Reciprocal Rank Fusion (RRF).
- **Redis Cache & Coordination:** Verifies rate-limit sliding windows, supplier list caching with TTL invalidation, and distributed locks.

### Layer 2: LangGraph Orchestration & Specialist Nodes
- **Specialist Runner:** Tests timeout boundaries (8s budget), retry exponential backoff, and partial failure isolation.
- **Comparison & Scoring:** Proves candidate ranking is 100% deterministic using frozen weights (`v1.0.0`).
- **Validation Node:** Enforces invariant boundaries (budget caps, valid quotations, certificate presence).
- **PostgreSQL Checkpointer:** Proves graph execution state is persisted to relational storage across process restarts.

### Layer 3: API Security & Governance
- **Authentication & RBAC:** Tests password hashing with Argon2id, JWT validation, and role-based endpoint gating (`requester`, `approver`, `auditor`, `admin`).
- **POL-002 Invariant:** Proves requesters are strictly rejected (HTTP 403) from approving their own purchase orders.
- **Idempotency Gate:** Proves repeated approval submissions with identical keys do not generate duplicate external ERP actions.

### Layer 4: React Frontend SPA
- **API Client:** Tests response deserialization, error envelope mapping, 401 callback clearing, and 429 Retry-After header parsing.
- **XSS & Content Safety:** Proves retrieved policy evidence is rendered strictly as plain text (script injection prevented).
- **Approval Decision UI:** Proves buttons remain disabled during in-flight requests, and reuses stable idempotency keys across retries.

---

## 3. Evaluation Harness Results (`scripts/run_evaluation.py`)

The evaluation harness executes 20 representative procurement cases against the full workflow engine:

| Metric Category | Target Invariant | Observed Score | Evaluation Result |
|---|---|---|---|
| **Mathematical Determinism** | Same input yields identical score every run | 100% (20/20) | PASS |
| **Hallucination Prevention** | Zero synthetic or invented vendor prices | 0% Hallucinated | PASS |
| **Policy Citation Grounding** | All cited chunk IDs exist in Qdrant | 100% Grounded | PASS |
| **Safety Abstention** | Inconclusive or absent evidence halts workflow | 100% Abstained | PASS |
| **Budget Enforcement** | Requests exceeding limits require approval or fail | 100% Enforced | PASS |

---

## 4. Failure Drill Observations (Phase 7 Drills 1–11)

1. **Expired Token:** UI intercepts 401, clears sessionStorage, and redirects user to `/login` with preserved state.
2. **Requester Self-Approval:** UI hides action button; direct cURL API attempt returns `HTTP 403 forbidden_self_approval`.
3. **Stale Recommendation (Race Condition):** Approval submitting outdated version returns `HTTP 409 Conflict`; UI prompts user to refresh.
4. **Duplicate Double-Click Approval:** Client button disables while pending; idempotency key ensures exactly 1 ERP order is emitted.
5. **Execution Timeout / Network Blip:** MCP execution failure transitions to `failed`; approver can click "Retry Execution" safely.
6. **Backend Server Down:** UI displays friendly error banner with status 0 and retry button, not a white screen of death.
7. **Qdrant Unreachable:** Retrieval specialist fails safely; workflow marks policy status `inconclusive` and halts before approval.
8. **MCP Service Down:** Approval decision is persisted in PostgreSQL; execution enters recoverable retry state without losing decision.
9. **XSS Injection Attempt in Evidence:** HTML/script tags in document body are rendered literally as text nodes via React DOM.
10. **Deep Link Browser Refresh:** Nginx SPA fallback routes `/workflows/xyz` to `index.html` without 404 errors.
11. **Compose Cold Start:** Pre-cached HuggingFace weights prevent cold start timeouts; all healthchecks pass within 45 seconds.

---

## 5. Non-Production Readiness Disclaimer

This test report verifies functional correctness against a local reference implementation. It does **not** certify:
- Production scale (>10,000 req/sec)
- High availability or automated disaster recovery
- Penetration testing or third-party compliance certification
