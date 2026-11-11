# Known Limitations: Agentic Procurement Reference Platform

This document honestly outlines the architectural and operational limitations of the current reference implementation. These constraints were chosen to preserve local-first reproducibility, test isolation, and cognitive clarity.

---

### 1. Authentication & Identity Management
- **Demo JWT Token Endpoint:** The system implements an internal HS256 token endpoint (`/api/v1/auth/login` and `/auth/token`) rather than federating to a production OpenID Connect (OIDC) or SAML identity provider (such as Okta, Keycloak, or Azure AD).
- **Static Shared Secret:** In local development, `JWT_SECRET_KEY` is loaded from `.env`. In production, this must be replaced with asymmetric RS256/ES256 keypairs with automated key rotation.
- **Session Revocation:** JWTs are stateless with a 60-minute lifetime. While Redis supports token blocklisting, fine-grained immediate session revocation across multiple browser tabs is not fully implemented.

---

### 2. ERP Action & External Execution
- **Simulated MCP Tool:** The Model Context Protocol gateway interacts with an internal mock ERP execution server. It creates simulated purchase order references (`PO-2026-XXXX`). Connecting to a live SAP S/4HANA or Oracle Cloud ERP system requires custom transport adapters, enterprise VPN gateways, and bilateral mutual TLS (mTLS).
- **Compensating Transactions:** While forward idempotency is guaranteed via unique idempotency keys, an automated two-phase rollback or cancellation protocol for already-submitted external ERP orders is not yet supported.

---

### 3. Machine Learning & Retrieval Models
- **Pretrained Embedding Weights:** Policy semantic search utilizes FastEmbed's `BAAI/bge-small-en-v1.5` dense model and BM25 sparse index. These models are general-purpose and have not been fine-tuned on specialized corporate legal or procurement vocabularies.
- **Structured Fields vs Free Text Extraction:** To prevent prompt injection and hallucinated contract terms, the primary procurement workflow accepts structured inputs (product ID, quantity, delivery days). Natural language extraction is intentionally bypassed in the core transaction path.

---

### 4. Concurrency, Scaling & High Availability
- **Client Polling vs Server-Sent Events:** The frontend UI monitors workflow progression via HTTP short-polling (every 2 seconds) rather than WebSocket or Server-Sent Events (SSE). While polling handles network reconnections and tab visibility cleanly, it increases idle request volume under high concurrency.
- **Single-Region Architecture:** All database services (PostgreSQL, MongoDB, Redis, Qdrant) are deployed as single-instance local containers without multi-region replication or automatic leader failover.

---

### 5. Policy Engine Sophistication
- **Role/Resource Access Control:** Approval authorization implements the core corporate requirement (POL-002: no requester self-approval, minimum approver role). However, it does not embed a general-purpose declarative policy engine (such as Open Policy Agent / Rego or AWS Cedar) for complex multi-tier matrix approvals (e.g., >$100k requiring VP and CFO co-signatures).

---

### 6. Compliance, Privacy & Telemetry
- **Synthetic Data Exclusively:** All suppliers, quotes, employee names, and corporate policies are generated synthetically. The system has not undergone SOC-2, ISO 27001, or GDPR compliance audits.
- **Telemetry Sink:** Structured JSON logs and Prometheus metrics are exposed on the host, but are not forwarded to an external managed SaaS (Datadog, Grafana Cloud, or OpenTelemetry Collector daemon).
