#!/usr/bin/env bash
# Phase 6 smoke test: start the stack, then token -> create request -> paused workflow.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/infrastructure/docker-compose.yml" --profile app)
BASE_URL="${BASE_URL:-http://localhost:8000}"
REQUESTER_EMAIL="${REQUESTER_EMAIL:-user0002@example.test}"
PASSWORD="${DEMO_USER_PASSWORD:-Password123!}"
START_STACK="${START_STACK:-1}"
WAIT_SECONDS="${WAIT_SECONDS:-120}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

json_field() {
  python3 -c 'import json,sys; data=json.load(sys.stdin); print(data'"$1"')'
}

if [[ "$START_STACK" == "1" ]]; then
  echo "Starting stack (profile: app)..."
  "${COMPOSE[@]}" up -d --build
fi

echo "Waiting for $BASE_URL/health/live (max ${WAIT_SECONDS}s)..."
deadline=$((SECONDS + WAIT_SECONDS))
until curl -fsS "$BASE_URL/health/live" >/dev/null 2>&1; do
  if (( SECONDS >= deadline )); then
    fail "API did not become live within ${WAIT_SECONDS}s"
  fi
  sleep 2
done

echo "Logging in as $REQUESTER_EMAIL..."
LOGIN_JSON="$(curl -fsS -X POST "$BASE_URL/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$REQUESTER_EMAIL\",\"password\":\"$PASSWORD\"}")" \
  || fail "login failed (did you run make seed / seed_user_credentials.py?)"
TOKEN="$(printf '%s' "$LOGIN_JSON" | json_field "['access_token']")"
[[ -n "$TOKEN" ]] || fail "login response contained no access token"

echo "Creating procurement request..."
CREATE_JSON="$(curl -fsS -X POST "$BASE_URL/api/v1/procurement/requests" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"product_id":"PRD0001","quantity":5}')" \
  || fail "request creation failed"
THREAD_ID="$(printf '%s' "$CREATE_JSON" | json_field "['thread_id']")"
[[ -n "$THREAD_ID" ]] || fail "create response contained no thread_id"

STATUS=""
for _ in $(seq 1 30); do
  WORKFLOW_JSON="$(curl -fsS "$BASE_URL/api/v1/workflows/$THREAD_ID" \
    -H "Authorization: Bearer $TOKEN")" || fail "workflow read failed"
  STATUS="$(printf '%s' "$WORKFLOW_JSON" | json_field "['status']")"
  if [[ "$STATUS" == "awaiting_approval" ]]; then
    echo "PASS: workflow $THREAD_ID paused at approval (status=$STATUS)"
    exit 0
  fi
  if [[ "$STATUS" == "failed" || "$STATUS" == "executed" || "$STATUS" == "rejected" || "$STATUS" == "inconclusive" ]]; then
    fail "workflow $THREAD_ID reached terminal status=$STATUS before approval"
  fi
  sleep 2
done

fail "workflow $THREAD_ID did not reach awaiting_approval (last status=$STATUS)"
