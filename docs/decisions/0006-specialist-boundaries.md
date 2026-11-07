# 0006 — Specialist context boundaries

- **Date:** 2026-11-07
- **Status:** accepted
- **Context:** Phase 4 splits the Phase 3 graph nodes into specialist services. Without
  explicit boundaries a specialist tends to grow into a god object: it receives the whole
  graph state, reaches for whichever repository is convenient, and quietly couples
  unrelated capabilities. The boundary has to be a type-level fact, not a convention.

## Decision

Every specialist communicates through frozen DTOs defined in `app/agents/contracts.py`.
A specialist never receives `ProcurementState`, a connection string, a user token, or
another specialist's private data. Nodes are the only place that reads graph state, and
they extract exactly the DTO fields the specialist needs.

| Specialist | Receives | Never receives |
|---|---|---|
| Supplier | `SupplierQuery` (product, category, quantity, constraints, as_of) | policy evidence, approval, user token, request history |
| Policy | `PolicyQuery` (text, filters, limit, as_of) | supplier prices, approval state, recommendation |
| Analysis | `ComparisonRequest` (request facts + candidate DTOs) | policy text, database clients, approval |
| Validation | `ValidationRequest` (comparison, recommendation, evidence metadata) | raw credentials, database clients |
| Explanation | comparison result, evidence DTOs, request facts | raw database access, credentials, approval state, tools |

Additional rules:

- No specialist writes approval or execution records; writes stay in the composition
  layer (`RecommendationService`, `ApprovalService`, `ExecutionService`).
- Specialists receive a repository or a service from the composition layer
  (`GraphDependencies`), never a connection string.
- DTO field names are asserted against a denylist (`FORBIDDEN_CONTEXT_FIELDS`) in
  `backend/tests/agents/test_context_boundaries.py`, so adding a forbidden field to a
  DTO fails the suite.
- The supplier port payload is additionally asserted to be a strict subset of the
  allowlist, proving the specialist does not forward extra state even when the caller
  overloads the request dict.

## Consequences

- Context leaks become test failures instead of review findings.
- Changing what a specialist may know requires a deliberate DTO edit plus a boundary
  test update — the friction is intentional.
- The runner and logging layer see only DTO-level metadata (codes, latencies, source ID
  counts), which keeps logs free of supplier rows, policy text, and tokens.
