"""Dense, sparse, and hybrid policy retrieval with metadata filters."""

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    DatetimeRange,
    FieldCondition,
    Filter,
    IsNullCondition,
    MatchAny,
    PayloadField,
)

from app.rag.embeddings import EmbeddingProvider, SparseEmbeddingProvider
from app.rag.fusion import FusedHit, RankedHit, reciprocal_rank_fusion
from app.rag.indexer import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME

DEFAULT_ALLOWED_CLASSIFICATIONS = ("public", "internal")


@dataclass(frozen=True)
class RetrievalFilters:
    statuses: tuple[str, ...] = ("active",)
    classifications: tuple[str, ...] = DEFAULT_ALLOWED_CLASSIFICATIONS
    as_of: date | None = None
    document_ids: tuple[str, ...] | None = None


def _datetime_value(value: date) -> str:
    return f"{value.isoformat()}T00:00:00Z"


class PolicyRetriever:
    def __init__(
        self,
        client: AsyncQdrantClient,
        dense: EmbeddingProvider,
        sparse: SparseEmbeddingProvider,
        *,
        collection_name: str,
        candidate_k: int = 20,
        rrf_k: int = 60,
        allowed_classifications: tuple[str, ...] = DEFAULT_ALLOWED_CLASSIFICATIONS,
    ) -> None:
        if candidate_k <= 0:
            raise ValueError("candidate_k must be positive")
        if rrf_k <= 0:
            raise ValueError("rrf_k must be positive")
        self.client = client
        self.dense = dense
        self.sparse = sparse
        self.collection_name = collection_name
        self.candidate_k = candidate_k
        self.rrf_k = rrf_k
        self.allowed_classifications = allowed_classifications

    def _validate_filters(self, filters: RetrievalFilters) -> None:
        disallowed = set(filters.classifications) - set(self.allowed_classifications)
        if disallowed:
            raise PermissionError(
                "classification not permitted: " + ", ".join(sorted(disallowed))
            )

    def build_filter(self, filters: RetrievalFilters) -> Filter | None:
        self._validate_filters(filters)
        conditions: list[Any] = []

        if filters.statuses:
            conditions.append(
                FieldCondition(key="status", match=MatchAny(any=list(filters.statuses)))
            )
        if filters.classifications:
            conditions.append(
                FieldCondition(
                    key="classification",
                    match=MatchAny(any=list(filters.classifications)),
                )
            )
        if filters.document_ids:
            conditions.append(
                FieldCondition(
                    key="document_id",
                    match=MatchAny(any=list(filters.document_ids)),
                )
            )
        if filters.as_of is not None:
            as_of = _datetime_value(filters.as_of)
            conditions.append(
                FieldCondition(
                    key="effective_from", range=DatetimeRange(lte=as_of)
                )
            )
            conditions.append(
                Filter(
                    should=[
                        IsNullCondition(is_null=PayloadField(key="effective_to")),
                        FieldCondition(
                            key="effective_to", range=DatetimeRange(gte=as_of)
                        ),
                    ]
                )
            )

        return Filter(must=conditions) if conditions else None

    @staticmethod
    def _normalize_query(query: str) -> str:
        normalized = " ".join(query.split())
        if not normalized:
            raise ValueError("query must not be empty")
        return normalized

    @staticmethod
    def _to_hits(points: list[Any]) -> list[RankedHit]:
        hits: list[RankedHit] = []
        for point in points:
            payload = dict(point.payload or {})
            hit_id = str(payload.get("chunk_id") or point.id)
            hits.append(
                RankedHit(chunk_id=hit_id, score=float(point.score), payload=payload)
            )
        return hits

    async def search_dense(
        self,
        query: str,
        *,
        filters: RetrievalFilters | None = None,
        limit: int | None = None,
    ) -> list[RankedHit]:
        normalized = self._normalize_query(query)
        if limit is None:
            limit = self.candidate_k
        if limit <= 0:
            raise ValueError("limit must be positive")

        vector = await self.dense.embed_query(normalized)
        response = await self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            using=DENSE_VECTOR_NAME,
            query_filter=self.build_filter(filters or RetrievalFilters()),
            limit=limit,
            with_payload=True,
        )
        return self._to_hits(list(response.points))

    async def search_sparse(
        self,
        query: str,
        *,
        filters: RetrievalFilters | None = None,
        limit: int | None = None,
    ) -> list[RankedHit]:
        normalized = self._normalize_query(query)
        if limit is None:
            limit = self.candidate_k
        if limit <= 0:
            raise ValueError("limit must be positive")

        vector = await self.sparse.embed_query(normalized)
        response = await self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            using=SPARSE_VECTOR_NAME,
            query_filter=self.build_filter(filters or RetrievalFilters()),
            limit=limit,
            with_payload=True,
        )
        return self._to_hits(list(response.points))

    async def search_hybrid(
        self,
        query: str,
        *,
        filters: RetrievalFilters | None = None,
        limit: int = 5,
        candidate_k: int | None = None,
    ) -> list[FusedHit]:
        normalized = self._normalize_query(query)
        if limit <= 0:
            raise ValueError("limit must be positive")
        candidates = max(limit, candidate_k or self.candidate_k)
        effective_filters = filters or RetrievalFilters()

        dense_hits, sparse_hits = await asyncio.gather(
            self.search_dense(normalized, filters=effective_filters, limit=candidates),
            self.search_sparse(normalized, filters=effective_filters, limit=candidates),
        )
        return reciprocal_rank_fusion(
            dense_hits, sparse_hits, k=self.rrf_k
        )[:limit]

    async def search(
        self,
        query: str,
        *,
        filters: RetrievalFilters | None = None,
        limit: int = 5,
        mode: Literal["dense", "sparse", "hybrid"] = "hybrid",
        candidate_k: int | None = None,
    ) -> list[FusedHit]:
        if mode == "hybrid":
            return await self.search_hybrid(
                query,
                filters=filters,
                limit=limit,
                candidate_k=candidate_k,
            )

        candidates = max(limit, candidate_k or self.candidate_k)
        if mode == "dense":
            hits = await self.search_dense(
                query, filters=filters, limit=candidates
            )
            return reciprocal_rank_fusion(hits, k=self.rrf_k)[:limit]
        if mode == "sparse":
            hits = await self.search_sparse(
                query, filters=filters, limit=candidates
            )
            return reciprocal_rank_fusion([], hits, k=self.rrf_k)[:limit]
        raise ValueError(f"unknown retrieval mode: {mode}")
