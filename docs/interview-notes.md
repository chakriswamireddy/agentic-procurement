# Interview Notes: Agentic Systems Engineering

This document outlines structural answers to the 14 core architectural questions for the Agentic Procurement reference platform. Every question follows the strict engineering framework:  
**Problem &rarr; Design Choice &rarr; Alternative Considered &rarr; Trade-Off &rarr; Implementation Evidence**.

---

### Q1: Why LangGraph instead of a simple function chain?
- **Problem:** Procurement requests are asynchronous and long-running. They require pausing for human approval (which may take hours or days) and must resume without losing in-flight state or re-executing expensive research.
- **Design Choice:** LangGraph with a persistent PostgreSQL checkpointer (`AsyncPostgresSaver`).
- **Alternative:** A simple async Python function chain or Celery task chain.
- **Trade-Off:** LangGraph introduces state graph abstractions and graph compilation overhead; however, it provides first-class interrupt/resume boundaries and conditional edge routing.
- **Evidence:** `backend/app/workflows/orchestrator.py` uses `builder.compile(checkpointer=checkpointer, interrupt_before=["execute_tool"])`.

---

### Q2: Why specialist nodes instead of autonomous agents?
- **Problem:** Autonomous multi-agent loops that plan their own steps are prone to infinite loops, tool hallucinations, unpredictable latency, and unbudgeted token consumption.
- **Design Choice:** Constrained specialist nodes with explicit schemas, dedicated roles (Supplier Catalog, Policy Retrieval, Invariant Validation), and bounded execution timeouts (8s).
- **Alternative:** An open-ended ReAct agent loop deciding which tools to call dynamically.
- **Trade-Off:** Specialists lack the open-ended reasoning of autonomous agents, but provide deterministic predictability, strict timeout bounds, and testable unit contracts.
- **Evidence:** `backend/app/specialists/runner.py` enforces `run_specialist_with_budget(timeout=8.0, retries=1)`.

---

### Q3: Which decisions must be deterministic?
- **Problem:** Financial procurement requires auditability. An LLM calculating unit prices, summing invoice totals, or ranking vendors on floating-point vibes creates legal liability and fraud vulnerabilities.
- **Design Choice:** All mathematical scoring, budget comparisons, eligibility checks, and approval authorization rules are strictly deterministic Python/SQL code (`SCORING_VERSION 1.0`). LLMs are restricted to read-only contextual summarization.
- **Alternative:** Allowing an LLM to evaluate supplier bids and output a winning vendor JSON.
- **Trade-Off:** Deterministic rules cannot interpret subtle qualitative nuances in supplier cover letters; however, they guarantee reproducibility and zero mathematical hallucination.
- **Evidence:** `backend/app/services/comparison_service.py` computes price, delivery, and risk scores via explicit weighted arithmetic.

---

### Q4: What is the source of truth for each data type?
- **Problem:** Distributed state across multiple databases causes split-brain data corruption if ownership boundaries are fuzzy.
- **Design Choice:** Strict single-ownership model:
  - *PostgreSQL:* Relational truth (Suppliers, Quotes, Requests, Recommendations, Audit Events, User Accounts).
  - *MongoDB:* Semi-structured profile truth (Vendor compliance certificates, tax registrations).
  - *Qdrant:* Derived policy retrieval index (Vector embeddings of policy documents).
  - *Redis:* Disposable cache, auth rate limits, and coordination locks.
- **Alternative:** Storing all documents as JSONB in PostgreSQL.
- **Trade-Off:** Multi-store operational overhead in Docker; but allows each store to excel at its specialized query workload.
- **Evidence:** `agentic-procurement/README.md` and repository interfaces in `backend/app/repositories/`.

---

### Q5: Why PostgreSQL and MongoDB together?
- **Problem:** Core supplier data and quotes require strict ACID relational integrity and foreign keys. Conversely, supplier compliance profiles (ISO certificates, environmental audits, regional registrations) vary wildly across international jurisdictions.
- **Design Choice:** PostgreSQL handles transactional consistency; MongoDB handles unstructured vendor document collections.
- **Alternative:** A purely relational schema with dozens of nullable join tables, or a pure document database.
- **Trade-Off:** Requires dual-store seeding and separate database clients; but preserves clean transactional tables while giving vendors flexible document schemas.
- **Evidence:** `backend/app/repositories/supplier_repository.py` and `backend/app/repositories/mongo_profile_repository.py`.

---

### Q6: How are checkpoints different from business records?
- **Problem:** LangGraph workflow execution state (active memory, node stack, thread history) is ephemeral to the run; enterprise business records (ProcurementRequest, Approval, AuditEvent) must outlive graph code refactors.
- **Design Choice:** Checkpoints are stored in LangGraph's internal `checkpoints` table for workflow resumption. Business records are normalized in `procurement_requests` and `audit_events`.
- **Alternative:** Storing business records directly inside the workflow state blob.
- **Trade-Off:** Redundant writes during state transitions; but decouples reporting queries and analytics from LangGraph framework serialization changes.
- **Evidence:** `backend/app/workflows/orchestrator.py` writes checkpoints; `backend/app/repositories/request_repository.py` maintains business tables.

---

### Q7: How do you prevent duplicate external actions?
- **Problem:** Network blips, user double-clicks, or container restarts can trigger duplicate purchase orders against the external ERP.
- **Design Choice:** Four-tier defense:
  1. Frontend buttons disable immediately upon submission.
  2. Idempotency key generated once upon user decision confirmation.
  3. PostgreSQL unique constraint on `(request_id, idempotency_key)` and row-level locking (`SELECT ... FOR UPDATE`).
  4. Optimistic concurrency control via `recommendation_version`.
- **Alternative:** Relying on the external ERP to detect duplicates.
- **Trade-Off:** Requires clients to manage idempotency tokens; but mathematically guarantees single execution.
- **Evidence:** `backend/app/services/workflow_service.py` validates `recommendation_version` and idempotency keys; tests in `test_concurrent_resume.py`.

---

### Q8: How do you establish a policy answer is evidence-backed?
- **Problem:** Vector search often retrieves weakly related text that LLMs hallucinate into false approvals.
- **Design Choice:** Calibrated hybrid retrieval (Dense + BM25 with Reciprocal Rank Fusion) combined with a hard abstention threshold (`min_score = 0.65`). If no chunks pass, the workflow transitions to `inconclusive`.
- **Alternative:** Top-K nearest neighbors without score thresholds.
- **Trade-Off:** May abstain on edge cases with poor vocabulary overlap; but prevents illegal or non-compliant purchase approvals.
- **Evidence:** `backend/app/services/policy_service.py` and `docs/decisions/0005-retrieval-threshold.md`.

---

### Q9: What happens if an MCP server or specialist fails?
- **Problem:** Specialist databases or external ERP MCP tools can timeout, crash, or return 500 errors.
- **Design Choice:** Bounded runner with exponential backoff retry and circuit-breaking. Specialist errors are captured in graph state (`issues`), allowing the validator to mark status as `needs_info` or `failed` rather than crashing the process.
- **Alternative:** Unhandled exceptions bubbling up to crash the FastAPI request.
- **Trade-Off:** Workflows halt in visible failure states; but system availability remains unaffected.
- **Evidence:** `backend/app/specialists/runner.py` and resilience tests in `test_resilience_outages.py`.

---

### Q10: How do OAuth, JWT, and application authorization fit together?
- **Problem:** Frontend client state cannot be trusted for financial authorization.
- **Design Choice:** Stateless JWT access tokens signed with HMAC-SHA256 containing user ID and role. The backend strictly evaluates authorization on every API call. Requester self-approval is blocked on JWT subject comparison.
- **Alternative:** Client-side role checking with local tokens.
- **Trade-Off:** Token revocation requires a blocklist; but keeps API requests stateless and scalable.
- **Evidence:** `backend/app/core/authz.py` (`ensure_can_approve`, `ensure_can_create_request`).

---

### Q11: Why Redis and Qdrant?
- **Problem:** Relational databases are inefficient for high-frequency sliding-window rate limiting and reciprocal rank vector similarity search.
- **Design Choice:** Redis provides atomic sub-millisecond in-memory sliding windows and catalog caching; Qdrant provides HNSW dense vector indexing alongside payload-filtered BM25 sparse search.
- **Alternative:** Using PostgreSQL `pgvector` for search and table locks for rate limiting.
- **Trade-Off:** Operational footprint of 4 services; but isolates CPU-intensive vector similarity and high-throughput cache spikes from transactional tables.
- **Evidence:** `backend/app/core/redis.py` and `backend/app/services/policy_service.py`.

---

### Q12: How do you evaluate beyond response fluency?
- **Problem:** High BLEU, ROUGE, or subjective LLM fluency scores mean nothing if the cited supplier quote or policy rule was hallucinated.
- **Design Choice:** Deterministic evaluation harness checking 5 hard invariants: (1) exact mathematical score reproducibility, (2) zero hallucinated pricing, (3) 100% policy chunk existence in Qdrant, (4) correct abstention on out-of-domain queries, and (5) budget enforcement.
- **Alternative:** Subjective LLM-as-a-judge scoring on qualitative answers.
- **Trade-Off:** Requires authoring formal test case datasets; but guarantees deterministic correctness.
- **Evidence:** `scripts/run_evaluation.py` (20/20 test cases passing).

---

### Q13: How would you scale long-running workflows?
- **Problem:** Under heavy load, in-memory worker pools run out of threads and memory.
- **Design Choice:** Checkpoints persist to PostgreSQL; graph execution runs on asynchronous event loops. In a distributed deployment, LangGraph threads are distributed across Celery/Temporal workers using thread IDs as routing keys.
- **Alternative:** Keeping graph state in server RAM.
- **Trade-Off:** Database I/O overhead on state checkpointing; but allows instances to scale horizontally and restart without dropping workflows.
- **Evidence:** `backend/app/workflows/orchestrator.py` compiled with `AsyncPostgresSaver`.

---

### Q14: What changes before connecting a real ERP?
- **Problem:** Moving from simulated MCP to live enterprise SAP or Oracle systems introduces security, legal, and operational compliance requirements.
- **Design Choice:**
  1. Replace HS256 JWT endpoint with corporate Okta/Azure AD OIDC.
  2. Implement mTLS (mutual TLS) and VPN gateways for ERP endpoints.
  3. Deploy asymmetric KMS keys for signing purchase requests.
  4. Implement an automated two-phase compensating transaction / reversal protocol for order cancellations.
  5. Conduct formal SOC-2 Type II audit and vulnerability penetration tests.
- **Evidence:** Documented in `docs/known-limitations.md`.
