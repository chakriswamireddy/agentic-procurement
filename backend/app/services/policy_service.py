import hashlib
import logging
import time
from datetime import date
from typing import Literal

from qdrant_client.http.exceptions import (
    ApiException,
    ResponseHandlingException,
    UnexpectedResponse,
)

from app.cache.redis_cache import RedisCache
from app.core.errors import (
    DependencyUnavailableError,
    ForbiddenError,
    ValidationError,
)
from app.rag.abstention import assess_evidence
from app.rag.citations import build_evidence, validate_evidence
from app.rag.embeddings import EmbeddingError
from app.rag.retriever import PolicyRetriever, RetrievalFilters
from app.schemas.policy import PolicySearchResponse

logger = logging.getLogger(__name__)

SearchMode = Literal["dense", "sparse", "hybrid"]
MIN_QUERY_LENGTH = 3
MAX_QUERY_LENGTH = 500
MAX_RESULTS = 20


class PolicyService:
    def __init__(
        self,
        retriever: PolicyRetriever,
        *,
        result_limit: int = 5,
        min_dense_score: float = 0.60,
        min_sparse_score: float = 2.0,
        min_text_chars: int = 40,
        cache: RedisCache | None = None,
    ) -> None:
        self.retriever = retriever
        self.result_limit = result_limit
        self.min_dense_score = min_dense_score
        self.min_sparse_score = min_sparse_score
        self.min_text_chars = min_text_chars
        self.cache = cache

    @staticmethod
    def _validate_query(query: str) -> str:
        normalized = " ".join(query.split())
        if len(normalized) < MIN_QUERY_LENGTH:
            raise ValidationError(
                f"query must be between {MIN_QUERY_LENGTH} and "
                f"{MAX_QUERY_LENGTH} characters"
            )
        if len(normalized) > MAX_QUERY_LENGTH:
            raise ValidationError(
                f"query must be between {MIN_QUERY_LENGTH} and "
                f"{MAX_QUERY_LENGTH} characters"
            )
        return normalized

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if not 1 <= limit <= MAX_RESULTS:
            raise ValidationError(f"limit must be between 1 and {MAX_RESULTS}")
        return limit

    async def search(
        self,
        query: str,
        *,
        limit: int | None = None,
        as_of: date | None = None,
        classifications: tuple[str, ...] | None = None,
        document_ids: tuple[str, ...] | None = None,
        mode: SearchMode = "hybrid",
    ) -> PolicySearchResponse:
        normalized = self._validate_query(query)
        effective_limit = self._validate_limit(
            self.result_limit if limit is None else limit
        )
        filters = RetrievalFilters(
            as_of=as_of,
            classifications=classifications or RetrievalFilters().classifications,
            document_ids=document_ids,
        )

        cache_key: str | None = None
        if self.cache is not None:
            parts = (
                normalized,
                str(effective_limit),
                mode,
                str(filters.as_of),
                str(sorted(filters.classifications or [])),
                str(sorted(filters.document_ids or [])),
            )
            raw_cache = ":".join(parts)
            cache_key = f"policy_search:{hashlib.sha256(raw_cache.encode()).hexdigest()}"
            cached_data = await self.cache.get(cache_key)
            if cached_data is not None:
                return PolicySearchResponse.model_validate(cached_data)

        started = time.perf_counter()
        try:
            hits = await self.retriever.search(
                normalized,
                filters=filters,
                limit=effective_limit,
                mode=mode,
            )
        except PermissionError as exc:
            raise ForbiddenError(str(exc)) from exc
        except (
            EmbeddingError,
            ApiException,
            ResponseHandlingException,
            UnexpectedResponse,
            OSError,
            TimeoutError,
            ConnectionError,
        ) as exc:
            logger.warning(
                "policy retrieval dependency unavailable",
                extra={"mode": mode, "error": exc.__class__.__name__},
            )
            raise DependencyUnavailableError("policy retrieval unavailable") from exc

        decision = assess_evidence(
            hits,
            min_dense_score=self.min_dense_score,
            min_sparse_score=self.min_sparse_score,
            min_text_chars=self.min_text_chars,
        )
        evidence = [] if decision.inconclusive else build_evidence(hits)
        if evidence:
            validate_evidence(evidence)

        logger.info(
            "policy search completed",
            extra={
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "mode": mode,
                "filters": {
                    "statuses": filters.statuses,
                    "classifications": filters.classifications,
                    "as_of": filters.as_of,
                    "document_ids": filters.document_ids,
                },
                "result_ids": [item.chunk_id for item in evidence],
                "inconclusive": decision.inconclusive,
                "reason": decision.reason,
            },
        )

        response = PolicySearchResponse(
            query=normalized,
            inconclusive=decision.inconclusive,
            reason=decision.reason,
            evidence=evidence,
        )
        if self.cache is not None and cache_key is not None and not decision.inconclusive:
            await self.cache.set(cache_key, response.model_dump(mode="json"))

        return response
