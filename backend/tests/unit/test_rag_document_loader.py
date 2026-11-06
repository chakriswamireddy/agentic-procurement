from datetime import date
from pathlib import Path

import pytest
import yaml
from app.rag.document_loader import (
    DocumentValidationError,
    load_document,
    load_documents,
)


def write_document(path: Path, **overrides: object) -> Path:
    metadata = {
        "document_id": "TST-001",
        "title": "Test Policy",
        "version": "1.0",
        "status": "active",
        "classification": "internal",
        "effective_from": "2026-01-01",
        "effective_to": None,
    }
    metadata.update(overrides)
    front_matter = yaml.safe_dump(metadata, sort_keys=False)
    path.write_text(f"---\n{front_matter}---\n\n# Test Policy\n\nBody text.\n", encoding="utf-8")
    return path


def test_load_document_parses_metadata_and_checksum(tmp_path: Path) -> None:
    path = write_document(tmp_path / "policy.md")

    document = load_document(path)

    assert document.document_id == "TST-001"
    assert document.title == "Test Policy"
    assert document.version == "1.0"
    assert document.status == "active"
    assert document.classification == "internal"
    assert document.effective_from == date(2026, 1, 1)
    assert document.effective_to is None
    assert document.body == "# Test Policy\n\nBody text."
    assert document.source_path == "policy.md"
    assert len(document.checksum) == 64


def test_missing_effective_from_names_file_and_field(tmp_path: Path) -> None:
    path = write_document(tmp_path / "bad.md")
    text = path.read_text(encoding="utf-8").replace("effective_from: '2026-01-01'\n", "")
    path.write_text(text, encoding="utf-8")

    with pytest.raises(DocumentValidationError) as excinfo:
        load_document(path)

    assert "bad.md" in str(excinfo.value)
    assert "effective_from" in str(excinfo.value)


def test_invalid_status_is_rejected(tmp_path: Path) -> None:
    path = write_document(tmp_path / "bad.md", status="deleted")

    with pytest.raises(DocumentValidationError) as excinfo:
        load_document(path)

    assert "status" in str(excinfo.value)


def test_invalid_document_id_is_rejected(tmp_path: Path) -> None:
    path = write_document(tmp_path / "bad.md", document_id="nope")

    with pytest.raises(DocumentValidationError) as excinfo:
        load_document(path)

    assert "document_id" in str(excinfo.value)


def test_effective_to_must_follow_effective_from(tmp_path: Path) -> None:
    path = write_document(
        tmp_path / "bad.md",
        effective_from="2026-01-01",
        effective_to="2025-12-31",
    )

    with pytest.raises(DocumentValidationError) as excinfo:
        load_document(path)

    assert "effective_to" in str(excinfo.value)


def test_oversized_file_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.rag.document_loader.MAX_FILE_SIZE_BYTES", 10)
    path = tmp_path / "big.md"
    path.write_text("---\n---\n" + "x" * 100, encoding="utf-8")

    with pytest.raises(DocumentValidationError) as excinfo:
        load_document(path)

    assert "size" in str(excinfo.value)


def test_non_markdown_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "policy.txt"
    path.write_text("content", encoding="utf-8")

    with pytest.raises(DocumentValidationError) as excinfo:
        load_document(path)

    assert ".md" in str(excinfo.value)


def test_duplicate_version_with_different_content_is_rejected(tmp_path: Path) -> None:
    write_document(tmp_path / "one.md")
    second = write_document(tmp_path / "two.md")
    second.write_text(
        second.read_text(encoding="utf-8").replace("Body text.", "Other text."),
        encoding="utf-8",
    )

    with pytest.raises(DocumentValidationError) as excinfo:
        load_documents(tmp_path)

    assert "duplicate" in str(excinfo.value)


def test_duplicate_version_with_identical_content_is_allowed(tmp_path: Path) -> None:
    write_document(tmp_path / "one.md")
    write_document(tmp_path / "two.md")

    documents = load_documents(tmp_path)

    assert len(documents) == 2
    assert documents[0].checksum == documents[1].checksum
