"""Evidence objects built only from retrieved Qdrant payloads.

Citations are never synthesized. Every evidence item is derived from a fused
retrieval hit and its payload, and any citation produced later (for example by a
grounded explanation) must reference a chunk ID that exists in that evidence
set.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.core.config import REPO_ROOT
from app.rag.fusion import FusedHit
from app.rag.prompts import detect_injection


class CitationValidationError(ValueError):
    """Raised when evidence or a citation does not match retrieved data."""


@dataclass(frozen=True)
class EvidenceItem:
    chunk_id: str
    document_id: str
    version: str
    title: str
    section_path: str
    text: str
    score: float
    dense_rank: int | None
    sparse_rank: int | None
    source_path: str
    effective_from: date
    effective_to: date | None
    dense_score: float | None = None
    sparse_score: float | None = None
    injection_suspected: bool = False
    status: str | None = None
    classification: str | None = None


def safe_source_path(value: str) -> str:
    """Return a repository-relative path; never expose a host absolute path."""
    path = Path(value)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def _required(payload: dict[str, Any], field: str, chunk_id: str) -> Any:
    value = payload.get(field)
    if value in (None, ""):
        raise CitationValidationError(
            f"chunk {chunk_id} payload is missing required field {field!r}"
        )
    return value


def _as_date(value: Any, field: str, chunk_id: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise CitationValidationError(
            f"chunk {chunk_id} has an invalid {field}: {value!r}"
        ) from exc


def evidence_from_hit(hit: FusedHit) -> EvidenceItem:
    payload = hit.payload
    payload_chunk_id = _required(payload, "chunk_id", hit.chunk_id)
    if str(payload_chunk_id) != hit.chunk_id:
        raise CitationValidationError(
            f"retrieved chunk id {hit.chunk_id} does not match payload "
            f"chunk_id {payload_chunk_id}"
        )

    effective_from = _as_date(
        _required(payload, "effective_from", hit.chunk_id),
        "effective_from",
        hit.chunk_id,
    )
    assert effective_from is not None
    text = str(_required(payload, "text", hit.chunk_id))
    return EvidenceItem(
        chunk_id=hit.chunk_id,
        document_id=str(_required(payload, "document_id", hit.chunk_id)),
        version=str(_required(payload, "version", hit.chunk_id)),
        title=str(_required(payload, "title", hit.chunk_id)),
        section_path=str(_required(payload, "section_path", hit.chunk_id)),
        text=text,
        score=hit.score,
        dense_rank=hit.dense_rank,
        sparse_rank=hit.sparse_rank,
        source_path=safe_source_path(
            str(_required(payload, "source_path", hit.chunk_id))
        ),
        effective_from=effective_from,
        effective_to=_as_date(payload.get("effective_to"), "effective_to", hit.chunk_id),
        dense_score=hit.dense_score,
        sparse_score=hit.sparse_score,
        injection_suspected=detect_injection(text),
        status=str(payload["status"]) if payload.get("status") else None,
        classification=(
            str(payload["classification"]) if payload.get("classification") else None
        ),
    )


def build_evidence(hits: Iterable[FusedHit]) -> list[EvidenceItem]:
    return [evidence_from_hit(hit) for hit in hits]


def validate_citations(
    cited_chunk_ids: Iterable[str],
    evidence: Sequence[EvidenceItem],
) -> None:
    """Reject any citation that is not part of the retrieved evidence set."""
    available = {item.chunk_id for item in evidence}
    fabricated = sorted({chunk_id for chunk_id in cited_chunk_ids} - available)
    if fabricated:
        raise CitationValidationError(
            "citations reference chunks that were not retrieved: "
            + ", ".join(fabricated)
        )


def validate_evidence(evidence: Sequence[EvidenceItem]) -> None:
    seen: set[str] = set()
    for item in evidence:
        if item.chunk_id in seen:
            raise CitationValidationError(f"duplicate evidence chunk {item.chunk_id}")
        seen.add(item.chunk_id)
        if not item.text.strip():
            raise CitationValidationError(f"evidence chunk {item.chunk_id} is empty")
