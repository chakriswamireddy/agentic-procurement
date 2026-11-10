from datetime import date

import pytest
from app.api.deps import get_current_user, get_current_user_optional, get_document_service
from app.schemas.auth import AuthenticatedUser
from app.schemas.document import PolicyDocumentRecord


def make_record(
    *,
    document_id: str = "TST-001",
    status: str = "active",
    ingestion_status: str = "registered",
) -> PolicyDocumentRecord:
    return PolicyDocumentRecord(
        id=document_id,
        version="1.0",
        title="Test Policy",
        status=status,
        classification="internal",
        effective_from=date(2026, 1, 1),
        source_path="data/documents/tst-001-v1.0.md",
        checksum="abc123",
        ingestion_status=ingestion_status,
    )


class FakeDocumentService:
    def __init__(self) -> None:
        self.uploaded: list[tuple[str, bytes]] = []
        self.record = make_record()

    async def upload(self, filename: str, content: bytes) -> PolicyDocumentRecord:
        self.uploaded.append((filename, content))
        return self.record

    async def list_documents(self, status=None):
        self.status = status
        return [self.record]

    async def get_document(self, document_id, version=None):
        self.requested = (document_id, version)
        return self.record

    async def ingest(self, document_id, version=None):
        self.ingested = (document_id, version)
        return make_record(ingestion_status="ingested")


@pytest.fixture
def fake_service() -> FakeDocumentService:
    return FakeDocumentService()


def _as(role="admin", user_id="USR0001"):
    user = AuthenticatedUser(id=user_id, email="user0001@example.test", role=role)
    return {
        get_current_user: (lambda u=user: u),
        get_current_user_optional: (lambda u=user: u),
    }


async def test_upload_document(application, api_client, fake_service) -> None:
    application.dependency_overrides[get_document_service] = lambda: fake_service
    application.dependency_overrides.update(_as("admin"))
    try:
        response = await api_client.post(
            "/api/v1/documents",
            files={"file": ("policy.md", b"# Policy\n", "text/markdown")},
        )
    finally:
        application.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["id"] == "TST-001"
    assert fake_service.uploaded[0][0] == "policy.md"


async def test_list_documents_with_status_filter(application, api_client, fake_service) -> None:
    application.dependency_overrides[get_document_service] = lambda: fake_service
    application.dependency_overrides.update(_as("admin"))
    try:
        response = await api_client.get(
            "/api/v1/documents", params={"status": "active"}
        )
    finally:
        application.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert fake_service.status == "active"


async def test_get_document_and_ingest(application, api_client, fake_service) -> None:
    application.dependency_overrides[get_document_service] = lambda: fake_service
    application.dependency_overrides.update(_as("admin"))
    try:
        detail = await api_client.get(
            "/api/v1/documents/TST-001", params={"version": "1.0"}
        )
        ingest = await api_client.post(
            "/api/v1/documents/TST-001/ingest", params={"version": "1.0"}
        )
    finally:
        application.dependency_overrides.clear()

    assert detail.status_code == 200
    assert fake_service.requested == ("TST-001", "1.0")
    assert ingest.status_code == 200
    assert ingest.json()["ingestion_status"] == "ingested"
    assert fake_service.ingested == ("TST-001", "1.0")