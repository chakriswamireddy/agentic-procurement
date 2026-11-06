from datetime import date
from types import SimpleNamespace

import pytest
from app.rag.retriever import PolicyRetriever, RetrievalFilters
from qdrant_client.models import FieldCondition, Filter, SparseVector


class FakeQdrantClient:
    def __init__(self, dense_points=None, sparse_points=None) -> None:
        self.dense_points = dense_points or []
        self.sparse_points = sparse_points or []
        self.calls: list[dict] = []

    async def query_points(self, **kwargs):
        self.calls.append(kwargs)
        points = (
            self.dense_points if kwargs["using"] == "dense" else self.sparse_points
        )
        return SimpleNamespace(points=points)


class FakeDenseProvider:
    dimension = 3

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed_documents(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]

    async def embed_query(self, text):
        self.queries.append(text)
        return [1.0, 0.0, 0.0]


class FakeSparseProvider:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed_documents(self, texts):
        return [SparseVector(indices=[1], values=[1.0]) for _ in texts]

    async def embed_query(self, text):
        self.queries.append(text)
        return SparseVector(indices=[1], values=[1.0])


def point(chunk_id: str, score: float) -> SimpleNamespace:
    return SimpleNamespace(id=f"id-{chunk_id}", score=score, payload={"chunk_id": chunk_id})


def make_retriever(client, dense=None, sparse=None) -> PolicyRetriever:
    return PolicyRetriever(
        client,
        dense or FakeDenseProvider(),
        sparse or FakeSparseProvider(),
        collection_name="policy_chunks",
        candidate_k=20,
        rrf_k=60,
    )


def test_default_filter_uses_active_public_internal() -> None:
    retriever = make_retriever(FakeQdrantClient())

    result = retriever.build_filter(RetrievalFilters())

    assert isinstance(result, Filter)
    keys = {condition.key for condition in result.must if isinstance(condition, FieldCondition)}
    assert keys == {"status", "classification"}


def test_as_of_filter_includes_effective_date_bounds() -> None:
    retriever = make_retriever(FakeQdrantClient())

    result = retriever.build_filter(RetrievalFilters(as_of=date(2026, 3, 1)))

    assert isinstance(result, Filter)
    keys = {condition.key for condition in result.must if isinstance(condition, FieldCondition)}
    assert keys == {"status", "classification", "effective_from"}
    assert any(isinstance(condition, Filter) for condition in result.must)


def test_document_id_filter_is_applied() -> None:
    retriever = make_retriever(FakeQdrantClient())

    result = retriever.build_filter(RetrievalFilters(document_ids=("POL-001",)))

    assert isinstance(result, Filter)
    keys = {condition.key for condition in result.must if isinstance(condition, FieldCondition)}
    assert "document_id" in keys


def test_disallowed_classification_is_rejected() -> None:
    retriever = make_retriever(FakeQdrantClient())

    with pytest.raises(PermissionError):
        retriever.build_filter(RetrievalFilters(classifications=("restricted",)))


async def test_hybrid_search_fuses_ranks_from_both_retrievers() -> None:
    client = FakeQdrantClient(
        dense_points=[point("A", 0.9), point("B", 0.8)],
        sparse_points=[point("B", 4.0), point("C", 3.0)],
    )
    dense = FakeDenseProvider()
    sparse = FakeSparseProvider()
    retriever = make_retriever(client, dense=dense, sparse=sparse)

    results = await retriever.search_hybrid("  approval   threshold ", limit=5)

    assert [item.chunk_id for item in results] == ["B", "A", "C"]
    assert results[0].dense_rank == 2
    assert results[0].sparse_rank == 1
    assert dense.queries == ["approval threshold"]
    assert sparse.queries == ["approval threshold"]
    assert all(call["query_filter"] is not None for call in client.calls)
    assert {call["using"] for call in client.calls} == {"dense", "sparse"}


async def test_dense_only_mode_reports_dense_ranks_only() -> None:
    client = FakeQdrantClient(dense_points=[point("A", 0.9), point("B", 0.8)])
    retriever = make_retriever(client)

    results = await retriever.search("approval threshold", mode="dense", limit=2)

    assert [item.chunk_id for item in results] == ["A", "B"]
    assert all(item.dense_rank is not None for item in results)
    assert all(item.sparse_rank is None for item in results)


async def test_sparse_only_mode_reports_sparse_ranks_only() -> None:
    client = FakeQdrantClient(sparse_points=[point("A", 4.0), point("B", 3.0)])
    retriever = make_retriever(client)

    results = await retriever.search("ISO14001", mode="sparse", limit=2)

    assert [item.chunk_id for item in results] == ["A", "B"]
    assert all(item.sparse_rank is not None for item in results)
    assert all(item.dense_rank is None for item in results)


async def test_empty_query_is_rejected() -> None:
    retriever = make_retriever(FakeQdrantClient())

    with pytest.raises(ValueError):
        await retriever.search_hybrid("   ")
