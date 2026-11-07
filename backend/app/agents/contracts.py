"""Specialist contracts: result envelope, error taxonomy, and narrow DTOs.

Contracts come first (phase 4, step 4.1). Each dataclass decides what a specialist is
allowed to know and return before any adapter is written, which is what makes the
context-boundary tests meaningful. Nothing here performs I/O, and every DTO maps to a
JSON-serializable shape at the graph-state boundary.

Error rules:

- ``code`` is stable and machine-readable (``supplier_db_unavailable``,
  ``policy_index_unavailable``, ``no_eligible_supplier``).
- Messages are safe for logs and users: no stack traces, SQL, or secrets.
- ``transient`` is a property of the error, not guessed at the call site by the runner.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from typing import Any

MAX_ERROR_MESSAGE_CHARS = 300

# Fields that must never appear on a specialist DTO. Kept here so the boundary test and
# the DTO definitions share one source of truth.
FORBIDDEN_CONTEXT_FIELDS = frozenset(
    {
        "approval",
        "approver_id",
        "credentials",
        "decision",
        "execution",
        "jwt",
        "password",
        "requester_id",
        "secret",
        "token",
        "user_id",
    }
)


class SpecialistError(Exception):
    """Base specialist failure with a stable machine-readable code."""

    code: str = "specialist_error"
    transient: bool = False

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = code or type(self).code
        self.message = " ".join(str(message).split())[:MAX_ERROR_MESSAGE_CHARS]
        self.details: dict[str, Any] = dict(details or {})
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "transient": self.transient,
            "details": dict(self.details),
        }


class TransientError(SpecialistError):
    """Timeout, connection reset, 429, 502/503/504 — safe to retry."""

    transient = True


class PermanentError(SpecialistError):
    """400/401/403/404, malformed input, missing config — retrying cannot help."""

    transient = False


class BusinessRuleError(SpecialistError):
    """The dependency answered, but a business rule makes the outcome unavailable."""

    code = "business_rule_violation"
    transient = False


class DependencyUnavailableError(TransientError):
    """The dependency is down or unreachable; a later attempt may succeed."""

    code = "dependency_unavailable"


@dataclass(frozen=True)
class SpecialistResult[T]:
    """Outcome envelope returned by the runner for every specialist call."""

    ok: bool
    data: T | None
    error: SpecialistError | None
    attempts: int
    latency_ms: int
    source_ids: tuple[str, ...] = ()

    @classmethod
    def success(
        cls,
        data: T,
        *,
        attempts: int,
        latency_ms: int,
        source_ids: tuple[str, ...] = (),
    ) -> SpecialistResult[T]:
        return cls(
            ok=True,
            data=data,
            error=None,
            attempts=attempts,
            latency_ms=latency_ms,
            source_ids=source_ids,
        )

    @classmethod
    def failure(
        cls,
        error: SpecialistError,
        *,
        attempts: int,
        latency_ms: int,
        source_ids: tuple[str, ...] = (),
    ) -> SpecialistResult[T]:
        return cls(
            ok=False,
            data=None,
            error=error,
            attempts=attempts,
            latency_ms=latency_ms,
            source_ids=source_ids,
        )

    def to_error_entry(self, *, node: str) -> dict[str, Any]:
        """Build the structured error record appended to graph state."""
        error = self.error or PermanentError("specialist failed")
        return {
            "code": error.code,
            "message": error.message,
            "node": node,
            "transient": error.transient,
            "attempts": self.attempts,
        }


# --------------------------------------------------------------------------------------
# Supplier DTOs
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SupplierQuery:
    """Everything the supplier specialist may know about a request. Nothing else."""

    product_id: str
    category: str
    quantity: int
    constraints: Mapping[str, Any]
    as_of: str

    @classmethod
    def from_request(
        cls, request: Mapping[str, Any], *, as_of: str
    ) -> SupplierQuery:
        return cls(
            product_id=str(request.get("product_id", "")),
            category=str(request.get("category", "")),
            quantity=int(request.get("quantity") or 0),
            constraints=dict(request.get("constraints") or {}),
            as_of=as_of,
        )

    def to_request_payload(self) -> dict[str, Any]:
        """Shape expected by the supplier repository port."""
        return {
            "product_id": self.product_id,
            "category": self.category,
            "quantity": self.quantity,
            "constraints": dict(self.constraints),
        }


@dataclass(frozen=True)
class SupplierCandidate:
    """One supplier quotation candidate. Candidates are never ranked here."""

    supplier_id: str
    supplier_name: str
    supplier_category: str
    supplier_status: str
    quotation_id: str
    product_id: str
    unit_price: str
    currency: str
    available_quantity: int
    delivery_days: int
    valid_until: str
    profile: Mapping[str, Any] | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SupplierCandidate:
        profile = payload.get("profile")
        return cls(
            supplier_id=str(payload.get("supplier_id", "")),
            supplier_name=str(payload.get("supplier_name", "")),
            supplier_category=str(payload.get("supplier_category", "")),
            supplier_status=str(payload.get("supplier_status", "")),
            quotation_id=str(payload.get("quotation_id", "")),
            product_id=str(payload.get("product_id", "")),
            unit_price=str(payload.get("unit_price", "")),
            currency=str(payload.get("currency", "")),
            available_quantity=int(payload.get("available_quantity") or 0),
            delivery_days=int(payload.get("delivery_days") or 0),
            valid_until=str(payload.get("valid_until", "")),
            profile=dict(profile) if isinstance(profile, Mapping) else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier_name,
            "supplier_category": self.supplier_category,
            "supplier_status": self.supplier_status,
            "quotation_id": self.quotation_id,
            "product_id": self.product_id,
            "unit_price": self.unit_price,
            "currency": self.currency,
            "available_quantity": self.available_quantity,
            "delivery_days": self.delivery_days,
            "valid_until": self.valid_until,
            "profile": dict(self.profile) if self.profile is not None else None,
        }


# --------------------------------------------------------------------------------------
# Policy DTOs
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyQuery:
    """Query text plus filters. No supplier data, no approval state."""

    text: str
    as_of: str
    limit: int = 5
    classifications: tuple[str, ...] = ()
    document_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PolicyEvidence:
    """A single cited chunk. Text without a chunk ID is never returned."""

    chunk_id: str
    document_id: str
    version: str
    section_path: str
    text: str
    score: float | None = None
    title: str = ""
    dense_rank: int | None = None
    sparse_rank: int | None = None
    source_path: str = ""
    effective_from: str = ""
    status: str = ""
    classification: str = ""
    injection_suspected: bool = False

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PolicyEvidence:
        chunk_id = str(payload.get("chunk_id") or "")
        if not chunk_id:
            raise PermanentError(
                "evidence item is missing a chunk id",
                code="invalid_policy_evidence",
            )
        score = payload.get("score")
        return cls(
            chunk_id=chunk_id,
            document_id=str(payload.get("document_id", "")),
            version=str(payload.get("version", "")),
            section_path=str(payload.get("section_path", "")),
            text=str(payload.get("text", "")),
            score=float(score) if score is not None else None,
            title=str(payload.get("title", "")),
            dense_rank=payload.get("dense_rank"),
            sparse_rank=payload.get("sparse_rank"),
            source_path=str(payload.get("source_path", "")),
            effective_from=str(payload.get("effective_from", "")),
            status=str(payload.get("status", "")),
            classification=str(payload.get("classification", "")),
            injection_suspected=bool(payload.get("injection_suspected")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyEvidenceResult:
    """Evidence plus an explicit inconclusive flag. Empty results are not errors."""

    query: str
    inconclusive: bool
    reason: str | None
    evidence: tuple[PolicyEvidence, ...]

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(item.chunk_id for item in self.evidence)

    def to_state(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "inconclusive": self.inconclusive,
            "reason": self.reason,
            "evidence": [item.to_dict() for item in self.evidence],
        }


# --------------------------------------------------------------------------------------
# Analysis and validation DTOs
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ComparisonRequest:
    """Request facts plus candidates. Never carries policy text or approval state."""

    request: Mapping[str, Any]
    candidates: tuple[SupplierCandidate, ...]
    as_of: str

    @classmethod
    def from_state(
        cls,
        *,
        request: Mapping[str, Any],
        candidates: list[Mapping[str, Any]],
        as_of: str,
    ) -> ComparisonRequest:
        return cls(
            request=dict(request),
            candidates=tuple(SupplierCandidate.from_dict(item) for item in candidates),
            as_of=as_of,
        )


@dataclass(frozen=True)
class ComparisonResult:
    """Deterministic comparison output. Eligible items keep the service's shape."""

    reason: str | None
    eligible_count: int
    eligible: tuple[Mapping[str, Any], ...]
    excluded: tuple[Mapping[str, Any], ...]
    recommended: Mapping[str, Any] | None
    rationale: Mapping[str, Any]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ComparisonResult:
        return cls(
            reason=payload.get("reason"),
            eligible_count=int(payload.get("eligible_count") or 0),
            eligible=tuple(payload.get("eligible") or ()),
            excluded=tuple(payload.get("excluded") or ()),
            recommended=payload.get("recommended"),
            rationale=dict(payload.get("rationale") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "eligible_count": self.eligible_count,
            "eligible": [dict(item) for item in self.eligible],
            "excluded": [dict(item) for item in self.excluded],
            "recommended": dict(self.recommended) if self.recommended else None,
            "rationale": dict(self.rationale),
        }


@dataclass(frozen=True)
class ValidationRequest:
    """Comparison, recommendation, and evidence metadata. No credentials."""

    request: Mapping[str, Any]
    comparison: Mapping[str, Any] | None
    recommendation: Mapping[str, Any] | None
    policy_status: Mapping[str, Any]
    policy_evidence: tuple[PolicyEvidence, ...]


@dataclass(frozen=True)
class ValidationResult:
    """Blocking and non-blocking issues with stable codes. Never mutates input."""

    sufficient: bool
    issues: tuple[Mapping[str, Any], ...]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ValidationResult:
        return cls(
            sufficient=bool(payload.get("sufficient")),
            issues=tuple(payload.get("issues") or ()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sufficient": self.sufficient,
            "issues": [dict(issue) for issue in self.issues],
        }


# --------------------------------------------------------------------------------------
# Explanation DTOs
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestFacts:
    """The subset of request data the explanation is allowed to see."""

    product_id: str
    product_name: str
    category: str
    quantity: int
    currency: str
    as_of: str

    @classmethod
    def from_request(
        cls, request: Mapping[str, Any], *, as_of: str
    ) -> RequestFacts:
        return cls(
            product_id=str(request.get("product_id", "")),
            product_name=str(request.get("product_name", "")),
            category=str(request.get("category", "")),
            quantity=int(request.get("quantity") or 0),
            currency=str(request.get("currency", "")),
            as_of=as_of,
        )


def dto_field_names(*dtos: type) -> set[str]:
    """All field names across the given DTO classes, for boundary assertions."""
    names: set[str] = set()
    for dto in dtos:
        names.update(field.name for field in fields(dto))
    return names
