# Five-Minute Demo Script: Agentic Procurement Platform

This script provides an exact, reproducible walkthrough of the Agentic Procurement reference platform. It demonstrates how autonomous specialists (PostgreSQL, MongoDB, Qdrant) safely cooperate under deterministic rules, human-in-the-loop approval (POL-002), and sandboxed Model Context Protocol (MCP) execution.

---

## Demo Setup & Prerequisites

Before starting the timer:
```bash
# 1. Reset and prepare demo data
bash scripts/prepare_demo.sh --yes

# 2. Verify all containers are up and healthy
docker compose -f infrastructure/docker-compose.yml --profile app up -d
curl -s http://localhost:8000/health/live
curl -s http://localhost:5173/healthz
```

**Demo Accounts (Password: `Password123!`):**
- **Requester:** `requester@example.com` (Role: `requester`)
- **Approver:** `approver@example.com` (Role: `approver`)

---

## 5-Minute Walkthrough Narrative

### Minute 0:00 – 1:00: Problem Context & Request Submission
1. **Open UI:** Navigate to `http://localhost:5173`.
2. **Explain Role:** *"Procurement teams struggle with balancing fast vendor selection against strict enterprise compliance, budget caps, and fraud prevention. LLMs are notoriously unreliable for financial authorization. Our architecture separates probabilistic extraction from deterministic authorization."*
3. **Sign In:** Click **Sign In**, select **Requester** demo profile, enter password `Password123!`.
4. **Submit Request:**
   - On the **New Request** screen, select:
     - **Product:** `Business Laptop 15" (PRD0001)`
     - **Quantity:** `50`
     - **Max Delivery Days:** `14`
     - **Required Certifications:** `ISO-9001`
   - Click **Submit Procurement Request**.
5. **Observation:** The browser navigates to `/workflows/:thread_id`. The status is initially `researching`, then transitions to `awaiting_approval`.

---

### Minute 1:00 – 2:00: Inspecting Multi-Store Evidence & Exclusions
1. **Timeline Inspection:**
   - Point to the live **Timeline**: *"Notice how LangGraph dispatched parallel specialist nodes for PostgreSQL supplier quotes and Qdrant policy retrieval before aggregating into deterministic comparison."*
2. **Suppliers Explorer (PostgreSQL vs MongoDB):**
   - In a second tab, open **Suppliers**. Search for the product or view candidate suppliers.
   - Show that core relational quotes (unit price, available capacity, delivery days) live in **PostgreSQL**.
   - Click **Explore Profile**: Show that flexible ISO certifications and compliance registrations are validated from **MongoDB** documents.
   - Point out excluded quotes: *"Notice expired quotes or insufficient capacities are excluded deterministically with machine reason codes."*
3. **Policy Evidence Citations (Qdrant):**
   - Return to the workflow screen and scroll to **Policy Evidence Citations**.
   - Show exact quoted sections from `POL-002` (e.g. section 3.4 governing independent sign-off).
   - Emphasize the trust badges:
     - 🛡️ **Verified Record** (database truth)
     - ⚙️ **Deterministic Compute** (rules-based weighted score, not LLM confidence)
     - 📜 **Policy Evidence** (vector-retrieved text rendered safely as text)

---

### Minute 2:00 – 3:00: Proving the Security Boundary (Self-Approval Violation)
1. **UI Behavior:**
   - Look at the **Human Approval Required** card at the bottom.
   - Note the prominent red warning: `POL-002 Self-Approval Prohibited`.
   - The Approve/Reject buttons are disabled because the current user created the request.
2. **Server-Side Enforcement Proof (Direct API call):**
   - Open a terminal and prove the UI is not the security boundary by attempting to bypass it via `curl`:
   ```bash
   # Extract requester token and attempt to approve directly
   REQ_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"email":"requester@example.com","password":"Password123!"}' | jq -r .access_token)

   curl -i -X POST http://localhost:8000/api/v1/workflows/<THREAD_ID>/approval \
     -H "Authorization: Bearer $REQ_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"decision":"approved","recommendation_version":1}'
   ```
   - **Result:** Returns `HTTP 403 Forbidden` with error code `forbidden_self_approval`.
   - Key Interview Point: *"The UI hiding the button is a convenience; the API strictly enforces POL-002 on the server."*

---

### Minute 3:00 – 4:00: Approver Authorization & MCP Execution
1. **Sign Out:** Click **Sign Out** in the header.
2. **Sign In as Approver:**
   - Select **Approver** demo profile (`approver@example.com`), enter `Password123!`.
3. **Approval Inbox:**
   - Click **Approval Inbox** (or deep link into `/workflows/:thread_id`).
   - Show the pending workflow item.
   - Click **Review & Decide**.
   - Review version `v1`, deterministic score `94.5/100`, total price, and vendor name.
   - Enter decision note: `"Approved within Q1 hardware refresh budget. Policy citations verified."`
   - Click **Approve & Execute (Idempotent)**.
4. **Execution Progression:**
   - Status transitions to `resuming` -> `executed`.
   - Timeline shows **MCP Execution** complete and **Result Recorded**.
   - The mock ERP external purchase order reference is written to the audit log.

---

### Minute 4:00 – 5:00: Idempotency, Invariants & Limitations
1. **Duplicate Execution Defense:**
   - Attempt to call the approval endpoint a second time with the same idempotency key or old version:
   - Server returns `HTTP 409 Conflict` (already decided / stale version). No second ERP order is created.
2. **Eval Results:**
   - Mention the 20-case deterministic eval harness (`scripts/run_evaluation.py`):
     - 100% deterministic score reproduction
     - Zero hallucinated quotes
     - Strict abstention when Qdrant policy evidence is below threshold
3. **Known Limitation:**
   - State honestly: *"This reference platform uses structured forms; natural language extraction is purposely isolated so prompt injections cannot manipulate unit prices or quantities."*

---

## Live Demo Fallback Matrix

| What Failed Live | Immediate Fallback | Narrative Explanation |
|---|---|---|
| **Stale version 409 during approval** | Refresh the browser page (`F5`) | *"This proves our optimistic concurrency control: the recommendation was invalidated, preventing double-spend."* |
| **Qdrant container slow / down** | Submit a request with empty constraints | *"Notice the system transitions to `inconclusive` rather than guessing or approving without evidence."* |
| **Network timeout / port busy** | Inspect via CLI: `bash scripts/verify_stack.sh` | Automated smoke script demonstrates the exact state transitions headless. |
