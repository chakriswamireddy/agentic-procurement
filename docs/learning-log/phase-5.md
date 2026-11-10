# Phase 5 learning log — Authentication, POL-002 Approval, and MCP Execution Gateway

- **Date:** 2026-11-10
- **Scope completed:** Steps 5.1–5.14 (Argon2 password hashing, PyJWT tokens, UserRepository,
  AuthService, auth endpoints, authenticated procurement requests, POL-002 self-approval
  prohibition, approval matrix validation, concurrent-resume locking, MCP server with five tools,
  independent approval verification at the MCP boundary, MCP client with schema validation and
  timeouts, execution retry path, resource-level authorization on all routes, authorization matrix
  decision record, credential seeding, and comprehensive unit/integration security tests)

## My explanation

Phase 5 replaces the development-only scaffolding from earlier phases with real production-grade
security, policy-compliant human-in-the-loop governance, and real external action via Model Context
Protocol (MCP). The requester identity is no longer an untrusted client field; it is derived from
cryptographically verified JWT access tokens signed with HMAC-SHA256 and backed by Argon2id password
hashing. When a workflow reaches `approval_interrupt`, resumption is strictly governed by Policy
POL-002: requesters are barred from self-approval (§ 1.3), rejections require actionable reasons
(§ 5.2), and stale recommendation versions are rejected with HTTP 409 Conflict. Furthermore, the
concurrency race condition identified in Phase 3 — where two simultaneous resume requests could
double-execute an order — is closed using PostgreSQL row-level locks (`SELECT ... FOR UPDATE`) and
immediate state transitioning to `resuming`.

Authorization is layered: role gates (`require_roles`) for coarse access, plus resource-level
helpers in `app/core/authz.py` (own-request read for requesters, admin-only document management,
self-approval blocked even for admins). The LLM never authorizes anything — the API authenticates
the human; the approval record authorizes the action; the MCP server re-checks approval before
creating anything. MCP tools raise `ToolError` so the SDK reports `is_error=True`; write tools
never accept business values (price, supplier, quantity) — only `request_id` + `idempotency_key`.

## Architecture and execution flow

```text
  [ Client / UI ]
        |
        | 1. POST /api/v1/auth/login (Argon2 verify -> PyJWT issue)
        v
  [ Bearer Token: sub=USR0002, role=requester, jti, iss, aud ]
        |
        | 2. POST /api/v1/procurement/requests (Header: Bearer <token>)
        |    - requester_id ALWAYS from JWT subject (not body)
        v
  [ Workflow: RequestValidation -> Specialists -> Join -> Compare -> Validation ]
        |
        v
  [ State: awaiting_approval (approval_interrupt) ]
        |
        | 3. POST /api/v1/workflows/{id}/approval (Header: Bearer <approver_token>)
        |    - CurrentUserDep + ensure_can_approve (role + self-approval)
        |    - recommendation version match (409 on stale)
        |    - Row lock (with_for_update) prevents concurrent resume double-execution
        v
  [ Graph Resume ] -> [ execute_tool ]
                            |
                            | 4. MCPExecutionGateway.create_purchase_request
                            v
              [ MCP Server tool: create_purchase_request ]
                            |  independent verify_approval_for_execution()
                            |  idempotency_key unique constraint
                            +--> Emits external_reference PO-...
                            v
  [ Terminal: record_result -> Status: executed ]
```

## What I implemented

- **5.1 Security utilities** (`app/core/security.py`):
  - Password hashing and verification with `argon2-cffi` (`PasswordHasher`).
  - JWT: HS256, TTL `jwt_ttl_minutes`, claims `sub/role/iss/aud/iat/exp/jti` (no email);
    issuer/audience validation; role allowlist; `jwt_secret` must be ≥32 bytes (validator).
- **5.2 User persistence and auth service** (`app/repositories/user_repository.py`,
  `app/services/auth_service.py`, `app/schemas/auth.py`):
  - `UserRepository` + `AuthService.authenticate` / async `verify_token` (reloads user, checks
    `is_active`).
  - `User.is_active` column (`001_schema.sql`, migration `003_user_is_active.sql`, seed).
- **5.3 Auth endpoints & FastAPI dependencies** (`app/api/v1/auth.py`, `app/api/deps.py`):
  - `POST /api/v1/auth/login` (JSON) and `POST /api/v1/auth/token` (OAuth2 form shape).
  - `GET /api/v1/auth/me`; deps `get_current_user`, `require_roles`, `CurrentUserDep`.
  - Auth rate limiting via Redis (`auth_rate_limit_*` settings; disabled in tests).
- **5.4 Authenticated request creation** (`app/api/v1/requests.py`):
  - `requester_id` always from JWT subject; body field removed (breaking change).
  - Only `requester`/`admin` may create requests (`ensure_can_create_request`).
- **5.5 Resource-level authorization** (`app/core/authz.py`):
  - `ensure_request_read` (requester owns, or privileged role; else 404 no-enumeration).
  - `ensure_can_approve` (approver/admin, never self → `self_approval_prohibited`).
  - `ensure_can_manage_documents` (admin only); `ensure_can_retry_execution`.
- **5.6 Concurrent resume race closure** (`app/services/workflow_service.py`):
  - `lock_for_resume` + status transition `awaiting_approval` → `resuming`; concurrent → 409.
- **5.7–5.11 MCP server, five tools, client** (`app/mcp/schemas.py`, `app/mcp/authz.py`,
  `app/mcp/server.py`, `app/mcp/client.py`):
  - Tools: `search_suppliers`, `get_supplier_quotation`, `get_policy_evidence`,
    `create_purchase_request`, `get_purchase_request_status`.
  - `create_purchase_request` input is only `request_id` + `idempotency_key`; independent
    approval verification; denials as `ToolError`.
  - Client: discovery, pydantic schema validation before invoke, timeouts, reconnect;
    structured error codes (`unknown_tool`, `invalid_arguments`, `server_unavailable`, …).
- **5.12 Execution gateway** (`app/services/mcp_gateway.py`, Settings):
  - In-process by default (`mcp_use_client=false`); optional stdio spawn
    (`MCP_SERVER_COMMAND/ARGS`, `MCP_TOOL_TIMEOUT_S`).
  - Terminal vs retryable error mapping.
- **5.13 Execution retry** (`WorkflowService.retry_execution`,
  `POST /workflows/{thread_id}/execution/retry`): admin/approver only; re-verifies approval.
- **5.14 Protected routes** (`requests`, `workflows`, `suppliers`, `policies`, `documents`):
  - Documents upload/ingest admin-only; list/get require authenticated roles.
  - Identity fields removed from approval body; `idempotency_key` on approval decision.
- **Decision record** `docs/decisions/0007-authorization-matrix.md`.
- **Credential seeding** `scripts/seed_user_credentials.py` (Argon2, production guards).
- **Security tests**:
  - `tests/integration/test_auth.py` — login, inactive user, garbage token, `/me`.
  - `tests/integration/test_authorization.py` — 404 no-enumeration, role matrix, admin
    self-approval 403, document admin-only.
  - `tests/integration/test_approval_idempotency_mcp.py` — approval flow, stale version,
    MCP five-tool discovery, unapproved create denied, same-key idempotent / different-key
    conflict (single `execution_records` row), execution retry.
  - `tests/unit/test_authorization.py`, `tests/unit/test_mcp_client.py`.

## Behaviour changes from Phase 4

| Component | Before (Phase 4) | After (Phase 5) | Why |
|---|---|---|---|
| Request creation | `requester_id` in JSON body | Derived from JWT claims | Clients cannot spoof identity |
| Approval API | Dev-only / weak checks | Authenticated + POL-002 + resource checks | Real governance; self-approval blocked for everyone |
| Documents | Any caller could upload | Admin-only write; authenticated read | Least privilege |
| Concurrent resume | Double-execution race | Postgres `FOR UPDATE` + status gate | Prevents duplicate PO |
| Execution gateway | Fake / single PO tool | MCP five tools + independent approval re-check | Trust boundary at tool server |
| MCP tool payload | Business fields accepted | Only `request_id` + `idempotency_key` | No untrusted business input at ERP edge |
| Token claims | Included email | sub/role/iss/aud/jti only | Minimize PII in tokens |

## Failure drills

| # | Drill | Observed behaviour |
|---|---|---|
| 1 | Self-approval (incl. admin) | HTTP 403 `self_approval_prohibited` |
| 2 | Requester/auditor approve | HTTP 403 role not permitted / self path |
| 3 | Foreign requester read | HTTP 404 (no enumeration) |
| 4 | Concurrent duplicate resume | Second → HTTP 409 not awaiting approval |
| 5 | Stale recommendation version | HTTP 409 |
| 6 | Rejection without reason | HTTP 422 |
| 7 | Tampered/expired/inactive token | HTTP 401 |
| 8 | MCP create without approval | ToolError denial (`approval` / `request_not_found`) |
| 9 | Same idempotency key twice | Single `execution_records` row; replay OK |
| 10 | Different key, same request | ToolError conflict; still one row |
| 11 | Non-admin document upload | HTTP 403 |
| 12 | Wrong password vs unknown user | Same 401 code/message (no user enumeration) |

## Trade-offs

- **`CurrentUserDep` + `ensure_can_approve` vs `require_roles`:** self-approval must return
  `self_approval_prohibited` (403) before generic role denial (POL-002 §1.3), including for
  admins who hold the approver role.
- **404 on foreign request read:** avoids resource-id enumeration by other requesters.
- **In-process MCP by default:** zero-ops local/tests; stdio client available via settings for
  process isolation when needed.
- **No email claim in JWT:** identity is `sub`; profile fetched from DB on each verify so
  role/`is_active` revocation takes effect without waiting for TTL.
- **Form `/token` + JSON `/login`:** demo OAuth2 shape for tooling compatibility without a
  full authorization server.

## Checkpoint answers

1. **How does Phase 5 prevent self-approval?**
   `ensure_can_approve` (and `ApprovalPolicyService`) require the authenticated subject
   (`JWT sub`) ≠ request `requester_id` and role in (`approver`, `admin`). Mismatch raises
   `ForbiddenError("self_approval_prohibited")` (HTTP 403) before resume.
2. **How is concurrent-resume double execution resolved?**
   `SELECT ... FOR UPDATE` on the request row; only `awaiting_approval` may transition to
   `resuming`; the loser sees non-awaiting status → HTTP 409.
3. **What is MCP's role, and how is approval re-checked?**
   MCP standardizes tool discovery/invocation. `create_purchase_request` calls
   `verify_approval_for_execution` independently of the API path and enforces idempotency —
   the LLM never authorizes.
4. **Why Argon2id?**
   Memory-hard, tunable cost, PHC winner; better against GPU/ASIC brute force than
   SHA-256/bcrypt alone.
5. **Why 404 instead of 403 for another user's request?**
   Prevents confirming that a request id exists to unauthorized requesters.

## Verification (end of Phase 5)

- `make test`: `ruff check .` clean; **335 passed**.
- Authorization matrix recorded in `docs/decisions/0007-authorization-matrix.md`.
