# Phase 3 learning log — LangGraph workflow and deterministic comparison

- **Date:** 2026-11-05
- **Scope completed:** Steps 3.1–3.14 (typed state, business records, comparison service,
  recommendation service, validation, graph nodes, routing, Postgres checkpointer,
  compiled graph, approval interrupt, execution gateway, workflow service, request and
  workflow APIs, graph tests)

## My explanation

Phase 3 turns separate services into one inspectable, resumable workflow. A typed
`ProcurementState` is the only thing the checkpointer persists; business facts
(requests, recommendations, approvals, executions, audit events) live in PostgreSQL and
must survive even if the checkpoint is lost. The graph fans out after request validation
into parallel supplier and policy research, merges in a join node, then runs a purely
deterministic comparison: eligibility rules with machine-readable reason codes decide
who may compete, and a versioned weighted score decides who wins. The LLM is not in this
loop at all. Validation recomputes the score defensively, checks evidence shape and
status, and either routes to an approval interrupt or to a terminal status. The approval
node calls LangGraph's `interrupt()`, which saves a checkpoint and stops; a later
`Command(resume=...)` re-enters only that node with the decision. Approved workflows
execute through an idempotent gateway interface; everything ends in `record_result`,
which writes the terminal status and audit event.

## Architecture and execution flow

```text
START
  |
validate_request ──── invalid ──────────────────────────> record_result -> END
  | valid (fan-out, same superstep)
  +--> supplier_lookup ──┐
  |                      +--> research_join --> compare_options
  +--> policy_retrieval ─┘         |                  |
        (errors merged by          | both failed      v
         Annotated reducer)        +---------> record_result
                                         validate_recommendation
                                                  | sufficient
                                                  v
                                         approval_interrupt (interrupt)
                                          | approved      | rejected/invalid
                                          v               v
                                   execute_tool ────> record_result -> END
```

Full diagram: `docs/architecture/graph.mmd`.

## What I implemented

- `ProcurementState` with `errors: Annotated[list[dict], operator.add]` as the only
  reducer; every other key has exactly one writer. All values are JSON-serializable.
- Business repositories: `procurement_requests`, `recommendations`,
  `approval_decisions`, `execution_records` (unique idempotency key), `audit_events`.
  `thread_id == request_id`, so a retried create resumes instead of duplicating.
- `ComparisonService`: ten eligibility rules with reason codes
  (`inactive_supplier` … `withdrawn_quotation`), Decimal scoring with weights
  `0.55/0.30/0.15`, risk map `low 100 / medium 70 / high 40 / unknown 50`, clamped and
  quantized to 2 decimals, deterministic tie-break
  (score, total cost, delivery days, supplier id), `SCORING_VERSION = "1.0"` in
  `scoring_config.py`.
- `build_policy_query` (deterministic, ≤300 chars, no LLM) and
  `RecommendationService` that persists version 1 before any approval pause.
- `RecommendationValidator`: nine checks covering request shape, eligibility,
  persistence, score recomputation, cost arithmetic, constraints, and evidence
  (required fields, no `obsolete`/`draft`), each with a machine-readable code.
- Nine thin graph nodes (no SQL/HTTP inside), pure routing functions, and
  `research_join` as the fan-in gate for the parallel superstep.
- `AsyncPostgresSaver` behind `checkpointer_context()` with its own connection string
  (`CHECKPOINTER_DATABASE_URL`), `setup()` at startup, `InMemorySaver` fallback for
  tests and disabled environments.
- Approval `interrupt()` with a secret-free payload; resume validates the decision
  shape and fails to `invalid_approval` rather than defaulting to approved.
- `ExecutionGateway` protocol with `FakeExecutionGateway`
  (`SIM-<request_id>-<version>`) and idempotency key `<request_id>:<version>`.
- `WorkflowService` (`create_and_start`, `start`, `get_status`, `resume`) merging
  graph state with PostgreSQL rows; request/workflow APIs; the resume endpoint is
  refused outside `APP_ENV=development`.

## Verification

```text
uv run ruff check .
All checks passed!

uv run pytest -q -m 'not integration'
166 passed, 34 deselected

uv run pytest -q -m integration
34 passed, 166 deselected

uv run pytest -q backend/tests/graph
24 passed
```

Test matrix coverage: invalid quantity → `needs_info` with no research calls; empty or
fully excluded candidates → `failed/no_eligible_supplier`; happy path → pause with
`__interrupt__`, persisted recommendation, payload carrying evidence chunk IDs; weak
policy evidence → `inconclusive` with no interrupt; approve → executed with one
gateway call; reject → `rejected` with no gateway call; invalid resume →
`failed/invalid_approval`; new graph instance reads and resumes the paused checkpoint;
looping test graph stops with `GraphRecursionError`; parallel branch errors both
survive the reducer; identical inputs produce byte-identical comparison JSON.

End-to-end API flow (live stack, seeded data, real Postgres checkpointer):

```text
POST /api/v1/procurement/requests  -> 201, X-Workflow-Status: awaiting_approval
GET  /api/v1/workflows/{id}        -> awaiting_approval, current_node approval_interrupt
POST /api/v1/workflows/{id}/approval (approved) -> executed; repeat -> 409
POST /api/v1/workflows/{id}/approval (rejected) -> rejected
```

## Failure drills

| # | Drill | Observed behaviour |
|---|---|---|
| 1 | Supplier service timeout | `supplier_lookup` appends `supplier_lookup_failed` and returns `[]`; no supplier is ever fabricated. With policy healthy, comparison reports `no_eligible_supplier`; with both branches failed, routing goes straight to `record_result` with `research_failed` |
| 2 | Policy service down | `policy_status = {inconclusive, reason: dependency_unavailable}`; validation yields `weak_policy_evidence`, status `inconclusive`, no approval interrupt |
| 3 | Checkpointer down | `checkpointer_context` fails at startup with a connection error instead of silently falling back to in-memory checkpoints |
| 4 | Process restart while paused | A second compiled graph with the same checkpointer (in-memory in unit tests, Postgres in integration) reads `awaiting_approval`, the recommendation, and `next == ("approval_interrupt",)`, and can resume |
| 5 | Duplicate resume | After a terminal status the API returns `409`; two *concurrent* resumes before the first commits can still double-execute — recorded as a Phase 5 idempotency gap |
| 6 | Invalid approval value | `{"decision": "maybe"}` and missing `approver_id` both fail to `failed/invalid_approval`; execution never runs; nothing defaults to approved |
| 7 | Graph recursion | A deliberately cyclic test graph raises `GraphRecursionError` at `recursion_limit=5` |
| 8 | Scoring drift | Reversing candidate order leaves the rationale byte-identical; changing price or delivery changes the score exactly as the weights dictate |

## Trade-offs

- **ContextVar dependency injection.** The compiled graph is process-wide but services
  hold request-scoped `AsyncSession`s. A context variable keeps them out of the graph
  object; asyncio copies context into the parallel branch tasks. The alternative —
  rebuilding the graph per request — would forfeit a compiled, inspectable artifact.
- **`thread_id == request_id`.** Simple and deterministic; a retried create resumes the
  existing run. The cost is that a genuinely new request must use a new request ID,
  which the `PRQ-<uuid>` scheme already guarantees.
- **Recommendation persisted before validation finishes.** The node persists first, so
  an inconclusive run can still leave a versioned recommendation row. Regeneration
  increments the version rather than overwriting, keeping history append-only.
- **One research branch failing is not fatal.** Only *both* failing short-circuits to
  `record_result`; a single failure still reaches comparison, where the empty eligible
  set produces the honest `no_eligible_supplier` outcome through validation.
- **`RetryPolicy(max_attempts=2)` on research nodes is narrow.** Nodes catch their own
  exceptions and convert them to structured errors, so retries only trigger for
  unexpected failures outside the `try` block. Approval and execution are deliberately
  not retried.
- **201 with the paused state** instead of separating creation and start into
  `202 Accepted`: one round trip for the demo, documented in the endpoint docstring.
- **Fake execution gateway.** Acceptable in Phase 3 because the interface and
  idempotency key are real; the final demo must swap in the MCP tool (Phase 5).

## Checkpoint answers

1. **Draw the graph and explain each edge.** See the diagram above: validation decides
   fan-out vs `needs_info`; both research branches must finish before `research_join`
   (LangGraph's superstep barrier); `after_research` only short-circuits when *both*
   branches failed; `after_validation` sends sufficient states to the interrupt and
   everything else to `record_result`; `after_approval` executes only on a valid
   `approved` decision; `after_execution` always records.
2. **Checkpoint vs thread ID vs business row.** A checkpoint is the serialized graph
   state plus metadata for one superstep, keyed by thread ID; the thread ID names one
   workflow run and is what you pass in `configurable`; the business row is the
   authoritative record in PostgreSQL. Losing checkpoints loses execution position,
   never approvals or recommendations.
3. **When do parallel branches merge, and why does `errors` need a reducer?** They
   merge at the fan-in node when every branch of the superstep has finished. Without
   `Annotated[..., operator.add]` the second branch's write would overwrite the first's
   error list; the reducer concatenates both.
4. **Which decisions are deterministic, and why must the LLM not own them?**
   Eligibility, scoring, ranking, tie-breaks, validation, and routing are all Python.
   The LLM must not own them because approvals and spend need reproducible,
   auditable, testable answers — an LLM's ranking cannot be recomputed or disputed.
5. **How does `interrupt()` work, and what is resumed?** It raises inside the node,
   LangGraph checkpoints the current state and stops; `ainvoke` returns
   `__interrupt__`. Resume re-enters *only that node*; `interrupt()` returns the value
   passed to `Command(resume=...)` as if it were the call's result.
6. **Why persist the recommendation before the interrupt?** The approval decision must
   reference a durable, versioned artifact. If the process dies during the pause, the
   approver and the resume path both reload from PostgreSQL, not from volatile state.
7. **Process death while paused / while executing?** Paused: the checkpoint plus the
   persisted recommendation make resume safe from any process sharing the checkpointer.
   Executing: the idempotency key and unique constraint make a re-invocation recover
   the existing execution row instead of double-purchasing (concurrent races remain a
   Phase 5 fix).
8. **How do you bound a runaway graph?** `recursion_limit` in every invocation config
   (25 by default); there are no cycles in Phase 3, and any future cycle must carry a
   hard step bound and a documented exit.
9. **Why is `thread_id` deterministic?** It equals `request_id`, so retried creates
   resume the same run instead of spawning parallel workflows over one business
   request.
10. **What is in `execution_records`, and why is the idempotency key unique?** Request
    ID, idempotency key `<request_id>:<version>`, external reference, status, error
    code. Uniqueness turns retry into lookup: a second call with the same key returns
    the first outcome.
11. **Why is the fake gateway acceptable now but not in the demo?** Phase 3 proves the
    workflow contract (interface, idempotency, failure handling) without a real
    procurement system. A demo that claims a purchase must exercise the real MCP tool
    behind the same interface.
12. **How do you test the reject path without a UI?** Drive the graph directly:
    run to the interrupt, then `ainvoke(Command(resume={"decision": "rejected", ...}))`
    and assert `status == "rejected"` with zero gateway calls — exactly what
    `test_resume_rejected_records_rejected_without_execution` does.

## Checkpoint score

**Self-assessed score: 88/100**

| Dimension | Score | Notes |
|---|---:|---|
| Conceptual understanding | 18/20 | Reducers, supersteps, interrupt/resume, and state-vs-business-DB boundaries are clear |
| Architecture and data flow | 15/15 | Topology, routing reasons, checkpointer ownership, and persistence order are explicit |
| Independent implementation | 23/25 | Full path works end to end; duplicate concurrent resume remains a known Phase 5 gap |
| Debugging and trade-offs | 17/20 | Eight drills recorded; checkpointer-outage and restart drills are automated, concurrent-resume race is reasoned |
| Interview explanation | 15/20 | Answers complete; needs more practice drawing the graph and justifying weights under time pressure |

This is above the Phase 3 threshold of 75.
