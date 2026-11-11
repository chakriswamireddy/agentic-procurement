# LangGraph Workflow Execution Walkthrough

This document breaks down each node and transition in the **LangGraph StateGraph** generated in [`langgraph_workflow.png`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/docs/architecture/langgraph_workflow.png) using a concrete, end-to-end procurement purchase example.

---

## 1. Concrete Example Scenario

| Attribute | Value |
| :--- | :--- |
| **Requester** | Alice (`usr_alice_eng`), Senior Staff Engineer |
| **Department** | Engineering |
| **Item** | 5 × `Business Laptop 15"` ([`PRD0001`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/data/seed/products.json)) |
| **Budget Limit** | ₹3,00,000 maximum spend |
| **Constraints** | Delivery within **14 business days**, vendor must hold active **`ISO-9001`** certification |
| **Request ID** | `req_2026_demo_001` |
| **Thread ID** | `th_procure_8849` |

---

## 2. Visual Workflow Map

```mermaid
flowchart TD
    START(["Start"]) --> validate_request["1. validate_request\n(Facts Extraction & Schema Validation)"]

    validate_request -.->|Parallel Fan-Out| supplier_lookup["2A. supplier_lookup\n(Postgres Quotes + Mongo Specs)"]
    validate_request -.->|Parallel Fan-Out| policy_retrieval["2B. policy_retrieval\n(Qdrant Hybrid Dense+Sparse RAG)"]
    validate_request -.->|Invalid Schema| record_result["8. record_result\n(Audit Telemetry & DB Persistence)"]

    supplier_lookup --> research_join["3. research_join\n(Barrier Sync & Partial-Failure Matrix)"]
    policy_retrieval --> research_join

    research_join -.->|Both Conclusive| compare_options["4. compare_options\n(Deterministic Pareto Scoring)"]
    research_join -.->|Research Failed| record_result

    compare_options --> validate_recommendation["5. validate_recommendation\n(Threshold Verification & LLM Grounding)"]

    validate_recommendation -.->|Spend > ₹2L (Needs Approval)| approval_interrupt["6. approval_interrupt\n(LangGraph Human-in-the-Loop Breakpoint)"]
    validate_recommendation -.->|Blocked| record_result

    approval_interrupt -.->|Manager Approved| execute_tool["7. execute_tool\n(MCP ERP PO Creation)"]
    approval_interrupt -.->|Rejected| record_result

    execute_tool -.-> record_result
    record_result --> END_NODE(["End"])

    classDef nodeClass fill:#f8f9fc,stroke:#4f46e5,stroke-width:2px,color:#1e1b4b;
    classDef terminal fill:#eef2ff,stroke:#312e81,stroke-width:2px,color:#1e1b4b;
    classDef paused fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#78350f;
    class START,END_NODE terminal;
    class approval_interrupt paused;
    class validate_request,supplier_lookup,policy_retrieval,research_join,compare_options,validate_recommendation,execute_tool,record_result nodeClass;
```

---

## 3. Step-by-Step Execution Walkthrough

### Step 1: `__start__` → `validate_request`
* **Source Code**: [`app/graph/nodes/validate_request.py`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/graph/nodes/validate_request.py)
* **What happens**:
  * Receives raw input payload from Alice.
  * Validates data types, item ID (`PRD0001`), positive quantities (`5`), and budget boundaries.
  * Establishes initial [`ProcurementState`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/graph/state.py) with correlation IDs and timestamps.
* **State Mutation**:
  ```json
  {
    "status": "researching",
    "request": {
      "product_id": "PRD0001",
      "quantity": 5,
      "max_budget": 300000,
      "required_certifications": ["ISO-9001"],
      "max_delivery_days": 14
    }
  }
  ```
* **Routing Decision**: [`after_validate_request()`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/graph/routing.py#L76-L79) fans out concurrently into **both** `supplier_lookup` and `policy_retrieval`.

---

### Step 2A: `supplier_lookup` (Parallel Branch 1)
* **Source Code**: [`app/graph/nodes/supplier_lookup.py`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/graph/nodes/supplier_lookup.py)
* **Retry Policy**: Up to 2 retry attempts with exponential backoff on network failures.
* **What happens**:
  1. Queries **PostgreSQL** relational tables for recent active supplier quotations for `PRD0001`.
  2. Queries **MongoDB** `supplier_catalog` collection for heterogeneous vendor attributes (ISO certifications, ESG scores, warranty extensions).
  3. Joins the relational and document models into unified candidate quotes:
* **Candidate Results Gathered**:
  * **Candidate 1 (TechCorp - `SUP0001`)**: ₹52,000/unit, 7 days delivery, `ISO-9001: True`, ESG rating: `A`
  * **Candidate 2 (ElectroSys - `SUP0002`)**: ₹58,000/unit, 10 days delivery, `ISO-9001: True`, ESG rating: `B`
  * **Candidate 3 (GlobalTech - `SUP0003`)**: ₹48,000/unit, 21 days delivery, `ISO-9001: False`
* **Edge**: Directly flows to `research_join`.

---

### Step 2B: `policy_retrieval` (Parallel Branch 2)
* **Source Code**: [`app/graph/nodes/policy_retrieval.py`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/graph/nodes/policy_retrieval.py)
* **What happens**:
  * Constructs a semantic policy search query: *"hardware laptop approval threshold certification requirements"*.
  * Runs **Hybrid Vector Retrieval** in **Qdrant**:
    * **Dense Embeddings**: `BAAI/bge-small-en-v1.5` (semantic concepts)
    * **Sparse Embeddings**: `Qdrant/bm25` (exact terms like "ISO-9001" and financial figures)
    * **Fusion**: Reciprocal Rank Fusion (RRF with $k=60$)
  * Verifies retrieved chunks against current policy version and calibration filters to prevent version leaks.
* **Retrieved Policy Evidence**:
  * `POL-001` (Section 3.2): *"Procurement requests totaling over ₹2,00,000 require Department Manager approval."*
  * `POL-002` (Section 1.4): *"Hardware suppliers must hold valid ISO-9001 quality management certification."*
* **Edge**: Directly flows to `research_join`.

---

### Step 3: `research_join` (Barrier Synchronization)
* **Source Code**: [`app/graph/nodes/research_join.py`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/graph/nodes/research_join.py)
* **What happens**:
  * Acts as a concurrency barrier awaiting the resolution of both asynchronous branches.
  * Evaluates the **Partial-Failure Matrix** defined in [`routing.py`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/graph/routing.py#L7-L20):
    * Supplier status: `ok` (3 candidates found)
    * Policy status: `ok` (conclusive evidence retrieved)
* **Routing Decision**: [`after_research()`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/graph/routing.py#L82-L83) routes cleanly to `compare_options`.

---

### Step 4: `compare_options` (Deterministic Math & Scoring)
* **Source Code**: [`app/graph/nodes/compare_options.py`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/graph/nodes/compare_options.py)
* **What happens**:
  * **No LLM in the math loop** — eliminates hallucination risks in procurement scoring.
  * **Step 1 - Hard Constraint Elimination**:
    * GlobalTech (`SUP0003`) eliminated: fails 14-day SLA (quoted 21 days) and lacks `ISO-9001`.
  * **Step 2 - Multi-Objective Scoring**:
    * TechCorp: Total = $5 \times 52,000 = ₹2,60,000$. Normalized score: **0.92**
    * ElectroSys: Total = $5 \times 58,000 = ₹2,90,000$. Normalized score: **0.78**
* **Result**:
  * Best Candidate: **TechCorp** (`SUP0001`)
  * Total Spend: **₹2,60,000** (Net savings: ₹40,000 under budget limit of ₹3,00,000)
* **Edge**: Unconditionally routes to `validate_recommendation`.

---

### Step 5: `validate_recommendation` (Guardrails & Explanation)
* **Source Code**: [`app/graph/nodes/validate_recommendation.py`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/graph/nodes/validate_recommendation.py)
* **What happens**:
  1. **Policy Threshold Audit**: Cross-checks total cost ₹2,60,000 against `POL-001` (Threshold ₹2,00,000).
     * `total_cost > threshold`: Sets `requires_approval = True` and flags role as `Engineering Manager`.
  2. **Grounded LLM Explanation**: Uses the LLM in an explanation-only capacity to draft human-readable justification referencing policy chunk IDs (`POL-001#L12`, `POL-002#L4`).
* **Routing Decision**: [`after_validation()`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/graph/routing.py#L86-L90) observes `validation["sufficient"] == True` with approval required, routing to `approval_interrupt`.

---

### Step 6: `approval_interrupt` (Human-in-the-Loop Breakpoint)
* **Source Code**: [`app/graph/nodes/approval.py`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/graph/nodes/approval.py)
* **What happens**:
  * Executes LangGraph's native breakpoint: `interrupt(_interrupt_payload(state))`.
  * **Execution Pauses**: The graph execution yields, and state is safely committed to the PostgreSQL Checkpointer.
  * Workflow enters status: **`awaiting_approval`**.
* **Human Action**:
  * Bob (Engineering Manager) opens the Web UI at `http://localhost:5173/requests/req_2026_demo_001`.
  * Reviews the recommendation summary, trust badges (`Verified Record`, `Computed Math`, `Policy Evidence`), and clicks **"Approve"**.
  * Frontend sends `POST /api/v1/requests/req_2026_demo_001/approve`.
  * Backend resumes LangGraph via `Command(resume={"decision": "approved", "approver_id": "usr_bob_mgr"})`.
* **Routing Decision**: [`after_approval()`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/graph/routing.py#L93-L99) detects `"approved"` and routes to `execute_tool`.

---

### Step 7: `execute_tool` (MCP Execution / ERP Dispatch)
* **Source Code**: [`app/graph/nodes/execute.py`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/graph/nodes/execute.py)
* **What happens**:
  * Enforces the hard safety rule: **Execution never runs without valid, verified human approval**.
  * Dispatches order payload via the Model Context Protocol (MCP) or backend execution client:
    ```json
    {
      "action": "create_purchase_order",
      "supplier_id": "SUP0001",
      "supplier_name": "TechCorp",
      "product_id": "PRD0001",
      "quantity": 5,
      "total_amount": 260000.00,
      "currency": "INR"
    }
    ```
  * ERP confirms creation: `PO_CONFIRMATION_REF = "PO-2026-ENG-8841"`.
  * Status set to: **`executed`**.
* **Routing Decision**: [`after_execution()`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/graph/routing.py#L102-L104) routes to `record_result`.

---

### Step 8: `record_result` → `__end__` (Persistence & Telemetry)
* **Source Code**: [`app/graph/nodes/record_result.py`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/graph/nodes/record_result.py)
* **What happens**:
  1. **Final DB Persistence**: Writes final execution state and PO reference to PostgreSQL `procurement_requests` table.
  2. **Audit Telemetry**: [`WorkflowTelemetry.emit_node_transition()`](file:///home/chakri/Documents/learn-ai-eng/agentic-procurement/backend/app/core/telemetry.py#L61-L114) records execution metrics (`duration_ms: 124.6`, `outcome: success`).
  3. **PII Sanitization**: Hashes user IDs (`anonymize_user_id()`) and strips sensitive auth headers (`recursive_redact()`).
* **Terminal Transition**: Edge connects to `__end__`. The workflow is complete!

---

## 4. Summary Matrix of Node Behavior

| Node | Type | Fault Tolerance | Output / Side Effect |
| :--- | :--- | :--- | :--- |
| **`validate_request`** | Validation | Terminal on bad schema | Sanitized facts, parallel branch trigger |
| **`supplier_lookup`** | Specialist | 2 Retries + Backoff | Candidate list from Postgres & MongoDB |
| **`policy_retrieval`** | Specialist | 2 Retries + Backoff | Ranked chunks from Qdrant Hybrid RAG |
| **`research_join`** | Barrier | Partial-Failure Matrix | Determines whether research is sufficient |
| **`compare_options`** | Deterministic | Timeout Budget | Ranked candidate quotes (no LLM math) |
| **`validate_recommendation`**| Guardrail | Graceful fallback | Policy check & grounded natural language explanation |
| **`approval_interrupt`** | Human-in-the-Loop| State Checkpointer | Freezes execution until manager approval |
| **`execute_tool`** | Dispatcher | Idempotent PO gateway | Generates Purchase Order in ERP |
| **`record_result`** | Audit/Telemetry | Non-blocking telemetry | Persists audit history and terminates graph |
