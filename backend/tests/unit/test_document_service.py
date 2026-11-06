from pathlib import Path

import pytest
from app.core.config import Settings
from app.core.errors import ConflictError, ValidationError
from app.schemas.document import PolicyDocumentRecord
from app.services.document_service import DocumentService

DOCUMENT = """---
document_id: TST-100
title: Test Policy
version: "1.0"
effective_from: 2026-01-01
effective_to: null
classification: internal
status: active
---

# Test Policy

## 1. Rules

A purchase requires approval from the line manager.
"""


class FakeDocumentRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], PolicyDocumentRecord] = {}

    async def upsert_document(self, document: PolicyDocumentRecord) -> None:
        self.rows[(document.id, document.version)] = document

    async def get_document(self, document_id: str, version: str | None = None):
        if version is not None:
            return self.rows.get((document_id, version))
        matches = [
            record
            for (record_id, _), record in self.rows.items()
            if record_id == document_id
        ]
        return matches[-1] if matches else None

    async def list_documents(self, status: str | None = None):
        records = list(self.rows.values())
        if status is not None:
            records = [record for record in records if record.status == status]
        return records


def make_service(tmp_path: Path) -> tuple[DocumentService, FakeDocumentRepository]:
    repository = FakeDocumentRepository()
    service = DocumentService(
        repository,  # type: ignore[arg-type]
        Settings(),
        documents_dir=tmp_path,
    )
    return service, repository


async def test_upload_saves_file_and_registers_document(tmp_path: Path) -> None:
    service, repository = make_service(tmp_path)

    record = await service.upload("policy.md", DOCUMENT.encode())

    assert record.id == "TST-100"
    assert record.ingestion_status == "registered"
    assert (tmp_path / "tst-100-v1.0.md").is_file()
    assert ("TST-100", "1.0") in repository.rows


async def test_upload_same_content_is_idempotent(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path)

    first = await service.upload("policy.md", DOCUMENT.encode())
    second = await service.upload("policy.md", DOCUMENT.encode())

    assert first.checksum == second.checksum
    assert len(list(tmp_path.glob("*.md"))) == 1


async def test_upload_changed_content_for_same_version_conflicts(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path)
    await service.upload("policy.md", DOCUMENT.encode())

    with pytest.raises(ConflictError):
        await service.upload(
            "policy.md",
            DOCUMENT.replace("line manager", "finance director").encode(),
        )


async def test_upload_rejects_non_markdown(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path)

    with pytest.raises(ValidationError):
        await service.upload("policy.pdf", b"%PDF")


async def test_upload_rejects_oversized_file(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path)

    with pytest.raises(ValidationError):
        await service.upload("policy.md", b"x" * (2 * 1024 * 1024 + 1))