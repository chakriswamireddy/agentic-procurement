# Phase 7 Learning Log: Frontend, Stabilization, and Interview Demo

**Phase:** Phase 7 (Frontend, Stabilization, and Interview Demo)  
**Status:** Completed  
**Rubric Score:** 96 / 100  

---

## 1. Checkpoint Self-Assessment

### Q1: Which parts of the UI are convenience, and which are security boundaries?
- **Answer:** The entire frontend UI (buttons, form validators, disabled states, hidden links) is strictly a **convenience layer**. The **security boundary** begins at the FastAPI API gateway and backend service layer:
  - Hiding the "Approve" button for a requester is UX convenience; the server rejecting direct POST `/workflows/:id/approval` with `HTTP 403 forbidden_self_approval` is the security boundary.
  - Client-side form bounds (`quantity <= 100000`) are convenience; Pydantic and PostgreSQL schema validations are the security boundaries.

### Q2: Where is the token stored, and what is the trade-off?
- **Answer:** The JWT access token is stored in **memory** (React state) and backed by **`sessionStorage`** for page refresh convenience.
  - *Trade-off:* `sessionStorage` avoids cross-tab leakage and persistence after tab closure (unlike `localStorage`), but remains readable by JavaScript running in the same origin. A hardened production alternative is `httpOnly` secure cookies with CSRF tokens, which was avoided here to keep the API stateless and CLI/Compose-friendly.

### Q3: Why does the approval button use the server's recommendation version?
- **Answer:** To prevent approving stale, mutated recommendations (optimistic concurrency control). If supplier prices or inventory changed while the human approver was reading the screen, the server increments `recommendation.version`. Submitting the old version returns `HTTP 409 Conflict`, forcing a refresh and preventing unintended budget commitments.

### Q4: Why is the idempotency key stable across retries?
- **Answer:** If a network timeout occurs while an approval request is in flight to the ERP, the user will click "Retry". If the client generated a new UUID on retry, the backend would treat it as a second distinct approval, potentially purchasing the items twice. Reusing the same idempotency key for the same user decision guarantees that the server deduplicates the action.

### Q5: How does polling stop, and what happens on tab hide/unmount?
- **Answer:** `usePolling` stops polling immediately upon entering terminal states (`awaiting_approval`, `approved`, `rejected`, `executed`, `failed`, `inconclusive`). On `document.visibilityState === 'hidden'`, polling timer pauses to conserve CPU and network; on visible, it resumes. On component unmount, `clearTimeout` is called and active requests are aborted.

### Q6: How do you distinguish verified facts, computed values, and AI text?
- **Answer:** Via explicit visual trust labels:
  - 🛡️ **Verified Record:** Primary transactional data directly from PostgreSQL / MongoDB (e.g. catalog quote, vendor location).
  - ⚙️ **Deterministic Compute:** Mathematical calculations (weighted scores, totals) evaluated by frozen Python code (`v1.0.0`).
  - 📜 **Policy Evidence:** Exact quoted text retrieved from Qdrant with document, version, and section citations.
  - 🤖 **AI-Generated Summary:** Natural language synthesis that does not alter scores or approvals.

### Q7: Why must evidence be rendered as text?
- **Answer:** Policy documents and vendor quotes can contain arbitrary user or external text. Using `dangerouslySetInnerHTML` would allow malicious vendors or compromised policy uploads to execute Cross-Site Scripting (XSS) attacks in the approver's browser. React DOM renders text nodes safely with automatic entity escaping.

### Q8: What does the UI do on 401, 403, 409, 429, and 503?
- **401:** Clears authentication state, deletes session token, and redirects to `/login` preserving the target path.
- **403:** Displays an "Access Denied" banner explaining server policy (e.g. self-approval prohibited under POL-002).
- **409:** Explains that the recommendation version changed or state was already decided, prompting a refresh.
- **429:** Inspects `Retry-After` header and disables action button with a countdown message.
- **503 / Network Error (0):** Shows friendly network error banner with a manual "Retry" button.

### Q9: How does the SPA reach the API in Compose, and why is there no CORS issue?
- **Answer:** The Nginx container serves the built React SPA and reverse-proxies `/api/*` to `http://backend:8000/api/*`. From the browser's viewpoint, API requests are made to the identical origin (`localhost:5173`), completely bypassing browser Cross-Origin Resource Sharing (CORS) preflight restrictions.

### Q10: Which invariant is easiest to break in the UI, and how is it enforced server-side?
- **Answer:** Requester self-approval (POL-002). An author can easily inspect element, enable a disabled button, or send a manual `curl` request. It is enforced on the server by decoding the authenticated JWT subject, comparing it against `request.requester_id`, and immediately returning HTTP 403 if they match.

### Q11: Walk through the five-minute demo from memory.
- **Answer:**
  1. Login as requester -> submit 50 Business Laptops with delivery constraint.
  2. Inspect live timeline -> parallel PG quotes and Qdrant policy retrieval.
  3. Inspect PostgreSQL quotes and MongoDB profiles -> show excluded expired quotes.
  4. Note paused approval state -> attempt requester approval -> show HTTP 403 Forbidden.
  5. Login as approver -> review deterministic score breakdown and version -> approve.
  6. Show MCP simulated ERP purchase order execution and audit record.

### Q12: What is the biggest known limitation, and how would you address it next?
- **Answer:** The simulated ERP gateway and internal demo HS256 JWT auth. Next step: integrate an OpenID Connect (OIDC) identity provider and build an enterprise transport adapter with mutual TLS for SAP/Oracle ERP integration.

### Q13: What would you test before claiming this is production-ready?
- **Answer:** High-concurrency load testing (>5,000 req/sec), third-party penetration testing, disaster recovery / failover drills across multi-region databases, and formal SOC-2 audit compliance.

### Q14: Which evaluation result would you show an interviewer, and why?
- **Answer:** The safety abstention and candidate exclusion test cases (`scripts/run_evaluation.py`). They prove that when inventory is insufficient or policy evidence is weak, the system safely halts with structured machine reason codes rather than hallucinating viable suppliers.

---

## 2. Failure Drill Observations (11 / 11 Complete)

| Drill # | Scenario | Expected Behavior | Observed Result |
|---|---|---|---|
| **Drill 1** | Expired JWT Token | UI clears session, redirects to `/login` | PASS: Intercepted in `client.ts`, redirected |
| **Drill 2** | Self-Approval Attempt | Requester cannot approve own order | PASS: UI disables button; direct API returns 403 |
| **Drill 3** | Stale Recommendation | Submitting outdated version | PASS: Returns 409 Conflict; UI instructs refresh |
| **Drill 4** | Duplicate Double-Click | Double click on Approve button | PASS: Button disables; exactly 1 ERP execution |
| **Drill 5** | Execution Timeout | MCP service disconnect | PASS: Workflow transitions to failed; retry enabled |
| **Drill 6** | Backend Down | API server unreachable | PASS: Status 0 error banner with retry |
| **Drill 7** | Qdrant Outage | Vector database offline | PASS: Specialist fails safely; status `inconclusive` |
| **Drill 8** | MCP Server Down | ERP gateway offline | PASS: Decision persisted; execution retry works |
| **Drill 9** | XSS Attempt | Malicious script tag in policy | PASS: Rendered literally as plain text node |
| **Drill 10** | SPA Deep Link | Refresh `/workflows/:id` in browser | PASS: Nginx `try_files` returns `index.html` |
| **Drill 11** | Compose Cold Start | First container boot | PASS: Air-gapped model cache avoids timeouts |

---

## 3. Rubric Self-Assessment (96 / 100)

- **Frontend Architecture & Security (25/25):** 5 required screens, typed API client, optimistic concurrency with versioning, XSS-safe text rendering, pessimistic approval flow.
- **Workflow & Specialist Coordination (25/25):** Parallel execution, deterministic scoring, policy evidence citations, MCP execution gateway.
- **Resilience, Containerization & Testing (24/25):** Multi-stage Nginx container, 17 frontend tests, 338 backend tests, 20 deterministic eval cases, smoke script. (-1 for short-polling over WebSockets).
- **Documentation & Interview Readiness (22/25):** Full demo script, architecture guide with Mermaid diagrams, test report, known limitations, and 14 interview question answers. (-3 for simulated ERP rather than live sandbox integration).
- **Total: 96 / 100 (Pass Gate)**
