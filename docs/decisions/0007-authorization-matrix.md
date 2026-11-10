# 0007 — Authorization Matrix

**Date:** 2026-11-10  
**Phase:** 5  
**Status:** Accepted

## Context

Phase 5 introduces JWT authentication, role checks, and resource-level
authorization. This document is the single source of truth for which
principals may call which routes.

## Roles

| Role | Intent |
|---|---|
| `requester` | Create and read own procurement requests |
| `approver` | Approve/reject others' requests; read any request |
| `admin` | All write operations except self-approval of own requests |
| `auditor` | Read-only everywhere |

## Matrix

| Route | Public | Requester | Approver | Admin | Auditor | Notes |
|---|---|---|---|---|---|---|
| `GET /health/*` | yes | yes | yes | yes | yes | Liveness/readiness |
| `POST /auth/token`, `POST /auth/login` | yes | yes | yes | yes | yes | Demo token endpoint; rate-limited |
| `GET /auth/me` | no | yes | yes | yes | yes | Requires valid JWT |
| `POST /procurement/requests` | no | own only | no | yes | no | `requester_id` from token only |
| `GET /procurement/requests/{id}` | no | own only | any | any | any | Other requester's ID → **404** (no enumeration) |
| `GET /workflows/{thread_id}` | no | own only | any | any | any | Same 404 policy as requests |
| `POST /workflows/{thread_id}/approval` | no | **no** | yes, not own | yes, not own | no | POL-002 self-approval ban; stale version → 409 |
| `POST /workflows/{thread_id}/execution/retry` | no | no | yes | yes | no | Same idempotency key; audit every retry |
| `GET /suppliers`, `GET /suppliers/{id}` | no | yes | yes | yes | yes | Authenticated read |
| `GET /documents`, `GET /documents/{id}` | no | yes | yes | yes | yes | Authenticated read |
| `POST /documents` | no | no | no | yes | no | Admin-only upload |
| `POST /documents/{id}/ingest` | no | no | no | yes | no | Admin-only ingest |
| `GET /policies/search` | no | yes | yes | yes | yes | Authenticated RAG search |

## Deviations from the draft matrix

- Approval endpoint uses `get_current_user` + `ensure_can_approve` rather than
  `require_roles` alone so that **self-approval returns 403
  `self_approval_prohibited`** (POL-002 §1.3) before the generic role denial.
- `requester_id` / `approver_id` request-body fields were **removed**; identity
  always comes from the JWT subject (breaking change vs Phase 3 shortcuts).
- Document list/get are authenticated for all roles (not admin-only reads) so
  auditors can review the registry.

## Error conventions

| Condition | Status | Body code |
|---|---|---|
| Missing/invalid token | 401 | `unauthorized` |
| Authenticated but forbidden role/resource | 403 | `forbidden` / domain code |
| Requester accessing another's resource | 404 | `not_found` |
| Stale recommendation version, duplicate non-idempotent resume | 409 | `conflict` / `stale_recommendation_version` |
| Schema/validation failure | 422 | `validation_error` |
| Auth rate limit exceeded | 429 | `rate_limited` |

## Audit

Every allow and deny decision on approval, document management, and execution
retry writes an `audit_events` row with actor, request ID, decision, reason
code, and correlation ID when available.
