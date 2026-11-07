# Phase 4 learning log — orchestration, specialists, and bounded failure handling

- **Date:** 2026-11-07
- **Scope completed:** Steps 4.1–4.13 (contracts, runner, supplier/policy/analysis/
  validation specialists, thin node adapters, orchestrator budgets, partial-failure
  routing, context boundaries, loop prevention, observability, grounded explanation)

## My explanation

Phase 4 turns the Phase 3 nodes into specialists behind explicit DTO contracts and makes
failure handling boring. The orchestrator is the graph topology plus routing plus
budgets — deliberately not a free-roaming LLM — because the workflow path must be
inspectable, testable, and bounded. Each specialist owns one capability and receives
only the DTO it needs: the supplier specialist returns candidates and never ranks them,
the policy specialist returns cited evidence and an `inconclusive` flag and never writes
an answer, the analysis specialist is pure deterministic scoring with no I/O, and the
validation specialist reports issues without mutating anything. The runner is the single
place where timeouts, capped retries (max 3), exponential backoff with jitter, and node
deadlines live, so every call returns a `SpecialistResult` instead of an unexpected
exception. The key behavioural change from Phase 3 is the partial-failure matrix: a
supplier outage terminates as `failed/supplier_unavailable`, a policy outage or weak
evidence terminates as `inconclusive/policy_unavailable` or
`policy_evidence_insufficient`, and both branches down is `research_unavailable` —
missing policy evidence never reaches comparison or approval, and zero candidates is
still a business outcome (`no_eligible_supplier`), not an operational failure. The one
controlled LLM use is a grounded explanation that can only summarize what the
deterministic comparison already decided; if it fails validation it falls back to a
template and the workflow does not notice.

## Architecture and execution flow

```text
START
  |
validate_request ── invalid ─────────────────────────────────────> record_result -> END
  | valid: plan = {research, budgets, reason}
  +--> supplier_lookup  ── SupplierSpecialist.search  ──┐
  |      run_specialist(timeout, attempts<=3, deadline)  |
  +--> policy_retrieval ── PolicySpecialist.retrieve ────┤
         run_specialist(...)                             |
                              research_join (fan-in) <───┘
                                    |
                          research_outcome matrix
                 +-----------+------+-----------+------------+
                 |           |      |           |            |
            compare_options |      |           |            |
                 |          v      v           v            v
            validate   supplier_  policy_  policy_   research_
                 |     unavail.   unavail. evidence_  unavailable
                 v      (failed) (inconcl.) insuff.    (failed)
   validate_recommendation (ValidationSpecialist)
                 | sufficient                    | blocking
                 v                               v
        approval_interrupt ── approved ──> execute_tool ──> record_result -> END
```

Budgets come from settings through `app/graph/orchestrator.py`
(`budgets_from_settings`), so no node hard-codes a number. The plan recorded in state
documents intent; it never spawns agents.

## What I implemented

- **4.1 Contracts** (`app/agents/contracts.py`): frozen `SpecialistResult[T]`, the error
  taxonomy (`SpecialistError`, `TransientError`, `PermanentError`, `BusinessRuleError`,
  `DependencyUnavailableError`) with stable codes and safe messages, and narrow DTOs
  (`SupplierQuery`, `SupplierCandidate`, `PolicyQuery`, `PolicyEvidence`,
  `PolicyEvidenceResult`, `ComparisonRequest/Result`, `ValidationRequest/Result`,
  `RequestFacts`). A `FORBIDDEN_CONTEXT_FIELDS` denylist backs the boundary tests.
- **4.2 Runner** (`app/agents/runner.py`): per-call `asyncio.wait_for` timeout, attempt
  cap of 3 regardless of caller, full-jitter backoff
  `min(max, base * 2**(attempt-1)) * (0.5 + random())`, node deadline that stops before
  sleeping past the budget, unexpected exceptions wrapped as
  `unexpected_specialist_error` without retry, one structured log line per attempt, and
  `SpecialistMetrics` for the per-workflow summary.
- **4.3 Supplier specialist**: validates the query, maps DB/dependency failures to
  `TransientError("supplier_db_unavailable")` and bad input to
  `PermanentError("invalid_supplier_query")`, caps candidates at 200, and returns
  candidates only. `SupplierProfileRepository.get_profiles` now batches Mongo lookups
  with `$in`, so candidate assembly issues one profile query instead of N+1.
- **4.4 Policy specialist**: builds filters, calls the Phase 2 hybrid retriever, returns
  evidence with an explicit `inconclusive` flag, drops `obsolete`/`draft` evidence as
  defense in depth, enforces the evidence cap, and maps index failures to
  `TransientError("policy_index_unavailable")`. Evidence without a `chunk_id` is a
  permanent error — text is never returned uncited.
- **4.5/4.6 Analysis and validation specialists**: thin deterministic wrappers; invalid
  input is `PermanentError("invalid_comparison_input")`, validation issues keep their
  Phase 3 codes.
- **4.7 Thin nodes**: each node extracts a DTO, calls `run_specialist` with its budget,
  and maps the result into a partial state update with an error entry carrying
  `code`, `node`, `transient`, and `attempts`. No SQL/HTTP in nodes; the execution node
  keeps a timeout but is never retried through the generic runner.
- **4.8 Orchestrator** (`app/graph/orchestrator.py`): owns topology, budgets, routing,
  termination, and the `plan` trace; documents why these are not autonomous agents and
  what would justify revisiting that.
- **4.9 Partial-failure routing** (`app/graph/routing.py`): `research_outcome()`
  implements the matrix as a pure function; `research_join` applies the terminal status
  and failure reason so routing and state can never disagree.
- **4.10 Context boundaries**: ADR `docs/decisions/0006-specialist-boundaries.md` plus
  tests asserting DTO allowlists, the forbidden-field denylist, and that the supplier
  port payload is a strict subset of what the specialist may see.
- **4.11 Loop prevention**: runner attempt cap 3, graph recursion limit 25 (settings),
  no node-to-node calls, terminal states, and a test that an always-transient operation
  stops after exactly 3 attempts.
- **4.12 Observability**: per-attempt logs with `correlation_id`, `thread_id`,
  `specialist`, `attempt`, `outcome`, `latency_ms`, `error_code`,
  `budget_remaining_ms`; `record_result` emits a summary with calls/retries/failures/
  elapsed. `_EXTRA_FIELDS` was extended so these keys survive the JSON/Human formatters.
- **4.13 Grounded explanation** (`app/agents/explanation_service.py`): prompt delimits
  evidence as untrusted data, temperature 0 / bounded tokens / 8 s timeout, JSON schema
  validation, cited `chunk_id` subset check, supplier-identity check, and a deterministic
  template fallback on any failure. Stored in `state["explanation"]` with
  `generated_by: "llm" | "template"`; it cannot touch score, eligibility, approval, or
  execution.

## Behaviour changes from Phase 3 (and why)

| Before | After | Why |
|---|---|---|
| One failed research branch still compared | supplier down → `failed/supplier_unavailable`, no comparison | Distinguish operational failure from "no supplier matches" |
| Weak/inconclusive policy still persisted a recommendation | policy problem → `inconclusive/...` before comparison | Never continue toward approval without policy evidence; no wasted persistence |
| Both failed → `research_failed` | `research_unavailable` | Matrix wording, machine-readable and specific |
| Validation ranked weak evidence above no-eligible | `no_eligible_supplier` wins | Matrix row "ok, empty \| any" is a business outcome |
| Errors identified by code only | errors carry `node` markers | Routing must tell *which branch* failed, not guess from codes |

## Failure drills

| # | Drill | Observed behaviour |
|---|---|---|
| 1 | Supplier timeout | Runner returns `supplier_timeout` after 3 bounded attempts; graph row 3 ends `failed/supplier_unavailable` with `supplier_results: []`, no comparison, no recommendation |
| 2 | Policy outage/timeout | `policy_status = {inconclusive: true, reason: dependency_unavailable}`, workflow ends `inconclusive/policy_unavailable`, zero approval interrupt, zero recommendation persistence |
| 3 | Both branches down | `research_join` records `failed/research_unavailable`, both branch errors present with node markers, `record_result` status `failed` |
| 4 | Permanent error | `PermanentError` stops after attempt 1 with zero sleeps; no retry of a bad request |
| 5 | Retry storm | 20 concurrent always-transient calls: every call exactly 3 attempts (60 failures total), 20 specialist calls, elapsed 43 ms — attempts bounded, no amplification beyond the cap |
| 6 | Process kill during retry | Server started with `MONGODB_URL` pointed at a black-hole IP (precheck: supplier detail `profile=null` after 3.05 s). SIGKILL of the real uvicorn PID 3 s into supplier attempt 1: curl died with exit 52, request row stayed `received`, 0 recommendations/approvals/executions, 3 checkpoints + 16 writes preserved. After restart `GET /workflows/...` returned 200 with `status=researching, current_node=supplier_lookup` from the checkpoint; resume at non-interrupt state correctly 404s; re-submission once mongo recovered completed `awaiting_approval` with SUP0001 |
| 7 | Unexpected exception | Wrapped as `unexpected_specialist_error`, logged with `correlation_id` and `attempt`, message contains no payload or stack trace (asserted in tests) |
| 8 | Context leak attempt | DTO denylist test fails if a forbidden field is added; supplier port payload test proves `token`/`approval`/`user_id` are not forwarded |

Observability check: a transient failure logs `attempt=1 outcome=error`, sleeps the
backoff, then `attempt=2`, with `correlation_id` present on every line and
`budget_remaining_ms` when a deadline is set.

**What drill 6 caught:** a Mongo outage raised `ServerSelectionTimeoutError`, which is
a `PyMongoError` — not `OSError`/`TimeoutError` — so it escaped the specialist's except
list and the runner wrapped it as a non-retryable `unexpected_specialist_error`. Fixed
in `SupplierCandidateService` by translating `PyMongoError` to
`DependencyUnavailableError` (the specialist already maps that to transient
`supplier_db_unavailable`), with a regression test asserting the composed path retries
3 times. The drill also exposed an ops trap: `kill $!` only kills the `uv run` wrapper
and orphans the real uvicorn child — drills must kill the listening PID from `ss`.

## Trade-offs

- **Specialists, not autonomous agents.** Requirements are known and bounded; loops
  would add nondeterminism and cost without a demonstrated need. Revisit only for
  open-ended discovery, unknown tool sequencing, or genuinely dynamic planning.
- **Policy inconclusive short-circuits before comparison.** Phase 3 persisted a
  recommendation even on weak evidence (append-only history); Phase 4 skips that work
  because the matrix forbids continuing toward approval, and the empty audit trail is
  the honest record. The cost: no recommendation row for inconclusive runs.
- **Empty candidates still run comparison.** The matrix allows either route; keeping
  comparison preserves an audit record of the empty eligible set and reuses the
  existing `no_eligible_supplier` validation path.
- **Retry only what is idempotent.** Supplier and policy reads are safe to retry;
  recommendation persistence and execution are not, so they keep single-shot handling
  with idempotency keys (Phase 5 adds the execution retry).
- **Attempt cap of 3 is global.** Callers cannot raise it; a retry storm is bounded by
  construction even if a future node passes a large `max_attempts`.
- **Explanation validation is pragmatic.** Supplier identity and citation subsets are
  enforced; a full numeric-consistency check over free text is not, because the
  deterministic rationale remains the authoritative explanation.
- **LLM provider is a protocol, not a client.** No model dependency is added in Phase 4;
  the template path is the default and the provider slot is filled in Phase 6/7.

## Checkpoint answers

1. **Why specialists rather than autonomous agents? What would justify changing that?**
   The workflow path, budgets, and failure modes are known in advance, so a static graph
   plus routing is inspectable, testable, and bounded. Autonomous loops would add
   nondeterminism, cost, and debugging surface with no demonstrated need. I would revisit
   for open-ended supplier discovery, heterogeneous tools with unknown sequencing, or
   tasks requiring dynamic planning.
2. **What does the orchestrator own, and what must it never do?** Owns topology, budget
   allocation, routing after research/validation, termination states, and the plan
   trace. Never invents supplier facts, scores suppliers, approves or executes, calls
   arbitrary LLM-chosen tools, or loops indefinitely.
3. **Which errors are retryable, and why is execution excluded?** Transient ones:
   timeouts, connection resets, 429/5xx, dependency-unavailable — the reads are
   idempotent, so a repeat is harmless. Execution creates money movement; retrying it
   through a generic runner could double-purchase, so it gets an idempotency key and a
   Phase 5-owned retry instead.
4. **How does the timeout budget differ from the retry count?** The per-call timeout
   bounds one attempt; the retry count bounds how many attempts may happen; the node
   deadline bounds total wall time including backoff sleeps. The deadline wins: the
   runner stops before sleeping past it even if attempts remain.
5. **Why does jitter matter?** Without it, concurrent callers retry on the same
   schedule and create a synchronized retry storm against an already-struggling
   dependency. Jitter spreads attempts over time; the cap on delay prevents any single
   wait from becoming unbounded.
6. **Walk through the partial-failure matrix.** Both branches down → `research_unavailable`
   (nothing trustworthy to act on); supplier down → `supplier_unavailable` (operational,
   distinct from an empty result); supplier ok but empty → comparison runs and yields
   `no_eligible_supplier` (business outcome); policy inconclusive → `inconclusive/
   policy_evidence_insufficient` before comparison (never approach approval without
   evidence); policy down → `inconclusive/policy_unavailable` (degrade, don't fail the
   whole request); validation failures → the specific validation reason. Every route is
   one test in `test_partial_failure_routing.py`.
7. **What context does each specialist receive, and why?** Supplier: product, category,
   quantity, constraints, as_of — enough to query, nothing to abuse. Policy: query text
   and filters — no prices or approval. Analysis: request facts and candidates — no
   policy text, no DB clients. Validation: comparison, recommendation, evidence metadata
   — no credentials. Minimum privilege keeps a compromised or buggy specialist from
   seeing or changing unrelated data.
8. **How do you prevent a retry storm from worsening an outage?** Hard attempt cap of 3
   per call, backoff with jitter and a delay cap, node deadlines that stop retries early,
   and retries only on errors marked transient by the taxonomy — the drill measured 20
   concurrent calls producing exactly 60 attempts in 43 ms.
9. **How do you prove the workflow cannot loop forever?** Graph recursion limit (25)
   stops cyclic topologies (`GraphRecursionError` test), the runner caps attempts at 3
   regardless of caller input, all transitions are edges (no node calls a node), and
   every path terminates in a terminal status consumed by `record_result`.
10. **Where do specialist failures appear for the operator, and what does the user see?**
    Structured logs per attempt with correlation ID, specialist, attempt, latency, error
    code, and budget remaining, plus a per-workflow summary. The user sees the workflow
    view's safe error messages (`supplier_unavailable`, `policy_unavailable`, …) with
    no stack traces, SQL, or payloads.
11. **Why is the analysis specialist pure, and how does that help testing?** No I/O, no
    clock beyond injected `as_of`, no LLM — identical inputs provably produce identical
    scores and rationale, which the determinism tests assert across calls and instances,
    and which makes scoring bugs reproducible with a table-driven test.
12. **What would you measure to split or merge a specialist?** Per-call latency
    distribution, retry and failure rates, change frequency (does one capability break
    when the other changes?), and team ownership. Split when one capability's failure
    modes or scaling differ; merge when they always change together and share the same
    budget.
13. **What can the LLM explanation change, and what must it never change?** Only the
    human-readable summary, key points, caveats, and cited chunk IDs. It must never
    change score, eligibility, recommendation version, approval, execution, or routing —
    it runs after status determination and its output is stored separately.
14. **How do you validate a citation from generated text? What happens when validation
    fails?** Every `cited_chunk_id` must be a subset of the chunk IDs actually supplied
    to the prompt; the supplier mentioned must match the deterministic recommendation.
    Any failure — malformed JSON, unknown chunk, wrong supplier, timeout — falls back to
    the deterministic template and logs a warning; the workflow continues unchanged.

## Checkpoint score

**Self-assessed score: 87/100**

| Dimension | Score | Notes |
|---|---:|---|
| Conceptual understanding | 18/20 | Taxonomy, budgets vs retries, matrix justification, and boundaries are solid; circuit-breaker theory was read but deliberately not implemented |
| Architecture and data flow | 15/15 | Contracts-first design, orchestrator ownership, and the matrix as a single pure function are explicit |
| Independent implementation | 23/25 | Full step list 4.1–4.13 delivered with tests; the LLM provider slot is a protocol rather than a real model call |
| Debugging and trade-offs | 17/20 | All eight drills recorded with real numbers; drill 6 caught a real taxonomy gap (PyMongoError not retryable) and an ops trap (`kill $!` orphans uvicorn) |
| Interview explanation | 14/20 | Answers written down; needs timed practice defending the matrix and the non-autonomous choice |

This is above the Phase 4 threshold of 75.

## Verification

```text
uv run ruff check .                    -> All checks passed
uv run pytest -q -m 'not integration'  -> 228 passed, 36 deselected
uv run pytest -q -m integration        -> 36 passed, 228 deselected
uv run pytest -q backend/tests/agents  -> 53 passed
```
