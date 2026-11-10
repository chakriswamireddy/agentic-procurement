from datetime import date

import pytest
from app.api.deps import get_current_user, get_current_user_optional, get_policy_service
from app.schemas.auth import AuthenticatedUser
from app.schemas.policy import EvidenceRead, PolicySearchResponse


class FakePolicyService:
    def __init__(self, response: PolicySearchResponse) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def search(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        return self.response


@pytest.fixture
def fake_response() -> PolicySearchResponse:
    return PolicySearchResponse(
        query="laptop approval",
        inconclusive=False,
        evidence=[
            EvidenceRead(
                chunk_id="chunk-1",
                document_id="POL-001",
                version="3.2",
                title="Procurement Policy",
                section_path="4.1 Thresholds",
                text="Procurement approver for laptops.",
                score=0.032,
                dense_rank=1,
                sparse_rank=2,
                source_path="data/documents/policy-001.md",
                effective_from=date(2026, 1, 1),
            )
        ],
    )


async def test_policy_search_returns_evidence(application, api_client, fake_response) -> None:
    service = FakePolicyService(fake_response)
    user = AuthenticatedUser(id="USR0001", email="user0001@example.test", role="admin")
    application.dependency_overrides[get_policy_service] = lambda: service
    application.dependency_overrides[get_current_user] = lambda: user
    application.dependency_overrides[get_current_user_optional] = lambda: user
    try:
        response = await api_client.get(
            "/api/v1/policies/search",
            params={"q": "laptop approval", "limit": 3},
        )
    finally:
        application.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["inconclusive"] is False
    assert body["evidence"][0]["chunk_id"] == "chunk-1"
    assert service.calls[0]["limit"] == 3


async def test_policy_search_passes_filters(application, api_client, fake_response) -> None:
    service = FakePolicyService(fake_response)
    user = AuthenticatedUser(id="USR0001", email="user0001@example.test", role="admin")
    application.dependency_overrides[get_policy_service] = lambda: service
    application.dependency_overrides[get_current_user] = lambda: user
    application.dependency_overrides[get_current_user_optional] = lambda: user
    try:
        response = await api_client.get(
            "/api/v1/policies/search",
            params=[
                ("q", "laptop approval"),
                ("classification", "internal"),
                ("document_ids", "POL-001"),
                ("as_of", "2026-01-01"),
            ],
        )
    finally:
        application.dependency_overrides.clear()

    assert response.status_code == 200
    call = service.calls[0]
    assert call["classifications"] == ("internal",)
    assert call["document_ids"] == ("POL-001",)
    assert call["as_of"] == date(2026, 1, 1)


async def test_policy_search_rejects_short_query(application, api_client, fake_response) -> None:
    application.dependency_overrides[get_policy_service] = lambda: FakePolicyService(
        fake_response
    )
    user = AuthenticatedUser(id="USR0001", email="user0001@example.test", role="admin")
    application.dependency_overrides[get_current_user] = lambda: user
    application.dependency_overrides[get_current_user_optional] = lambda: user
    try:
        response = await api_client.get(
            "/api/v1/policies/search", params={"q": "ab"}
        )
    finally:
        application.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_policy_search_rejects_large_limit(application, api_client, fake_response) -> None:
    application.dependency_overrides[get_policy_service] = lambda: FakePolicyService(
        fake_response
    )
    user = AuthenticatedUser(id="USR0001", email="user0001@example.test", role="admin")
    application.dependency_overrides[get_current_user] = lambda: user
    application.dependency_overrides[get_current_user_optional] = lambda: user
    try:
        response = await api_client.get(
            "/api/v1/policies/search",
            params={"q": "laptop approval", "limit": 21},
        )
    finally:
        application.dependency_overrides.clear()

    assert response.status_code == 422