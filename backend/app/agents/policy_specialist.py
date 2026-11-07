"""Policy specialist: hybrid retrieval with explicit inconclusive signalling.

Evidence only — no answer generation, no paraphrasing, no approval decision. An empty or
weak result is a successful call with ``inconclusive=True``, never an exception, so a
policy outage degrades to an inconclusive workflow instead of a confident recommendation.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Protocol

from qdrant_client.http.exceptions import (
    ApiException,
    ResponseHandlingException,
    UnexpectedResponse,
)

from app.agents.contracts import (
    PermanentError,
    PolicyEvidence,
    PolicyEvidenceResult,
    PolicyQuery,
    SpecialistError,
    TransientError,
)
from app.core.errors import AppError, DependencyUnavailableError
from app.rag.embeddings import EmbeddingError

logger = logging.getLogger(__name__)

MAX_EVIDENCE_DEFAULT = 5
# Defense in depth: the retriever already filters these, but non-current evidence must
# never reach a recommendation even if a port misbehaves.
DISALLOWED_EVIDENCE_STATUSES = frozenset({"obsolete", "draft"})


class PolicyPort(Protocol):
    """Composition-layer port mirroring ``PolicyService.search``."""

    async def search(
        self,
        query: str,
        *,
        limit: int | None = None,
        as_of: date | None = None,
        classifications: tuple[str, ...] | None = None,
        document_ids: tuple[str, ...] | None = None,
        mode: str = "hybrid",
    ) -> Any: ...


class PolicySpecialist:
    """Narrow policy capability: filters, retrieval, evidence, inconclusive flag."""

    name = "policy_retrieval"

    def __init__(
        self, port: PolicyPort, *, max_evidence: int = MAX_EVIDENCE_DEFAULT
    ) -> None:
        self.port = port
        self.max_evidence = max_evidence

    async def retrieve(self, query: PolicyQuery) -> PolicyEvidenceResult:
        if not query.text.strip():
            raise PermanentError("query text is required", code="invalid_policy_query")
        if query.limit <= 0:
            raise PermanentError("limit must be positive", code="invalid_policy_query")

        try:
            as_of = date.fromisoformat(query.as_of)
        except ValueError as exc:
            raise PermanentError(
                "as_of must be an ISO date", code="invalid_policy_query"
            ) from exc

        try:
            response = await self.port.search(
                query.text,
                limit=min(query.limit, self.max_evidence),
                as_of=as_of,
                classifications=query.classifications or None,
                document_ids=query.document_ids or None,
            )
        except SpecialistError:
            raise
        except DependencyUnavailableError as exc:
            raise TransientError(
                "policy index unavailable",
                code="policy_index_unavailable",
                details={"cause": type(exc).__name__},
            ) from exc
        except AppError as exc:
            raise PermanentError(
                "invalid policy query",
                code="invalid_policy_query",
                details={"cause": type(exc).__name__},
            ) from exc
        except PermissionError as exc:
            raise PermanentError(
                "policy index access denied",
                code="invalid_policy_query",
                details={"cause": type(exc).__name__},
            ) from exc
        except (
            EmbeddingError,
            ApiException,
            ResponseHandlingException,
            UnexpectedResponse,
            TimeoutError,
            ConnectionError,
            OSError,
        ) as exc:
            raise TransientError(
                "policy index unavailable",
                code="policy_index_unavailable",
                details={"cause": type(exc).__name__},
            ) from exc

        items: list[PolicyEvidence] = []
        for item in list(getattr(response, "evidence", None) or []):
            payload = (
                item.model_dump(mode="json")
                if hasattr(item, "model_dump")
                else dict(item)
            )
            if str(payload.get("status", "")).lower() in DISALLOWED_EVIDENCE_STATUSES:
                continue
            items.append(PolicyEvidence.from_dict(payload))
            if len(items) >= self.max_evidence:
                break

        return PolicyEvidenceResult(
            query=str(getattr(response, "query", None) or query.text),
            inconclusive=bool(getattr(response, "inconclusive", False)),
            reason=getattr(response, "reason", None),
            evidence=tuple(items),
        )
