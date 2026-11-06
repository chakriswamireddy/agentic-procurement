"""Load and validate policy Markdown documents with YAML front matter."""

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from app.core.config import REPO_ROOT

MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024
ALLOWED_STATUSES = frozenset({"active", "obsolete", "draft"})
ALLOWED_CLASSIFICATIONS = frozenset({"public", "internal", "restricted"})
DOCUMENT_ID_PATTERN = re.compile(r"^[A-Z]{2,10}-\d{3,}$")
REQUIRED_FIELDS = (
    "document_id",
    "title",
    "version",
    "status",
    "classification",
    "effective_from",
)


class DocumentValidationError(ValueError):
    """Raised when a policy source file fails validation."""

    def __init__(self, path: Path, field: str, message: str) -> None:
        self.path = path
        self.field = field
        super().__init__(f"{path.name}: {field}: {message}")


@dataclass(frozen=True)
class LoadedDocument:
    document_id: str
    title: str
    version: str
    status: str
    classification: str
    effective_from: date
    effective_to: date | None
    body: str
    source_path: str
    checksum: str


def _as_date(value: Any, path: Path, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise DocumentValidationError(
                path, field, "must be an ISO date (YYYY-MM-DD)"
            ) from exc
    raise DocumentValidationError(path, field, "must be an ISO date (YYYY-MM-DD)")


def _source_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return path.name


def _parse_front_matter(path: Path, text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise DocumentValidationError(path, "front_matter", "missing YAML front matter")

    try:
        end = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration as exc:
        raise DocumentValidationError(
            path, "front_matter", "unterminated YAML front matter"
        ) from exc

    try:
        metadata = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as exc:
        raise DocumentValidationError(path, "front_matter", "invalid YAML") from exc

    if not isinstance(metadata, dict):
        raise DocumentValidationError(path, "front_matter", "must be a YAML mapping")

    missing = sorted(field for field in REQUIRED_FIELDS if metadata.get(field) in (None, ""))
    if missing:
        raise DocumentValidationError(
            path, "front_matter", f"missing required fields: {', '.join(missing)}"
        )

    body = "\n".join(lines[end + 1 :]).strip()
    if not body:
        raise DocumentValidationError(path, "body", "document body is empty")
    return metadata, body


def load_document(path: Path) -> LoadedDocument:
    path = Path(path)
    if path.suffix.lower() != ".md":
        raise DocumentValidationError(path, "file", "only .md documents are supported")
    if not path.is_file():
        raise DocumentValidationError(path, "file", "file does not exist")

    raw = path.read_bytes()
    if len(raw) > MAX_FILE_SIZE_BYTES:
        raise DocumentValidationError(
            path,
            "file",
            f"exceeds maximum size of {MAX_FILE_SIZE_BYTES} bytes",
        )

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentValidationError(path, "file", "must be valid UTF-8") from exc

    metadata, body = _parse_front_matter(path, text)

    document_id = str(metadata["document_id"]).strip()
    if not DOCUMENT_ID_PATTERN.match(document_id):
        raise DocumentValidationError(
            path, "document_id", "must match ^[A-Z]{2,10}-\\d{3,}$"
        )

    status = str(metadata["status"]).strip()
    if status not in ALLOWED_STATUSES:
        raise DocumentValidationError(
            path, "status", f"must be one of {', '.join(sorted(ALLOWED_STATUSES))}"
        )

    classification = str(metadata["classification"]).strip()
    if classification not in ALLOWED_CLASSIFICATIONS:
        raise DocumentValidationError(
            path,
            "classification",
            f"must be one of {', '.join(sorted(ALLOWED_CLASSIFICATIONS))}",
        )

    effective_from = _as_date(metadata["effective_from"], path, "effective_from")
    effective_to = (
        None
        if metadata.get("effective_to") in (None, "")
        else _as_date(metadata["effective_to"], path, "effective_to")
    )
    if effective_to is not None and effective_to <= effective_from:
        raise DocumentValidationError(
            path, "effective_to", "must be after effective_from"
        )

    return LoadedDocument(
        document_id=document_id,
        title=str(metadata["title"]).strip(),
        version=str(metadata["version"]).strip(),
        status=status,
        classification=classification,
        effective_from=effective_from,
        effective_to=effective_to,
        body=body,
        source_path=_source_path(path),
        checksum=hashlib.sha256(raw).hexdigest(),
    )


def load_documents(directory: Path) -> list[LoadedDocument]:
    """Load every Markdown document in a directory in stable filename order.

    A repeated ``(document_id, version)`` is allowed only when the checksums are
    identical. Different content for the same version is rejected because it
    makes the source of truth ambiguous.
    """
    directory = Path(directory)
    documents: list[LoadedDocument] = []
    seen: dict[tuple[str, str], LoadedDocument] = {}

    for path in sorted(directory.glob("*.md")):
        document = load_document(path)
        key = (document.document_id, document.version)
        previous = seen.get(key)
        if previous is not None and previous.checksum != document.checksum:
            raise DocumentValidationError(
                path,
                "document_id/version",
                f"duplicate {document.document_id} version {document.version} "
                f"with different content (also in {previous.source_path})",
            )
        seen[key] = document
        documents.append(document)
    return documents
