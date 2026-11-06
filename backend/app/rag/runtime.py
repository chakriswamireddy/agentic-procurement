from qdrant_client import AsyncQdrantClient

from app.core.config import Settings
from app.database.qdrant.client import init_qdrant
from app.rag.embeddings import (
    EmbeddingProvider,
    FastEmbedDenseProvider,
    FastEmbedSparseProvider,
    SparseEmbeddingProvider,
)
from app.rag.retriever import PolicyRetriever

_dense: EmbeddingProvider | None = None
_sparse: SparseEmbeddingProvider | None = None


def init_embedding_providers(
    settings: Settings,
) -> tuple[EmbeddingProvider, SparseEmbeddingProvider]:
    global _dense, _sparse
    if _dense is None:
        _dense = FastEmbedDenseProvider(
            settings.embedding_model,
            settings.embedding_dim,
            cache_dir=settings.fastembed_cache_dir or None,
            batch_size=settings.embedding_batch_size,
            timeout_seconds=settings.embedding_timeout_seconds,
        )
    if _sparse is None:
        _sparse = FastEmbedSparseProvider(
            settings.sparse_embedding_model,
            cache_dir=settings.fastembed_cache_dir or None,
            batch_size=settings.embedding_batch_size,
            timeout_seconds=settings.embedding_timeout_seconds,
        )
    return _dense, _sparse


def get_embedding_providers(
    settings: Settings,
) -> tuple[EmbeddingProvider, SparseEmbeddingProvider]:
    return init_embedding_providers(settings)


def get_qdrant_client(settings: Settings) -> AsyncQdrantClient:
    return init_qdrant(settings)


def build_retriever(settings: Settings) -> PolicyRetriever:
    dense, sparse = get_embedding_providers(settings)
    return PolicyRetriever(
        get_qdrant_client(settings),
        dense,
        sparse,
        collection_name=settings.qdrant_collection,
        candidate_k=settings.retrieval_candidate_k,
        rrf_k=settings.rrf_k,
    )


def reset_runtime() -> None:
    global _dense, _sparse
    _dense = None
    _sparse = None
