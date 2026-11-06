"""Dense and sparse embedding providers with batching and timeouts."""

import asyncio
import threading
from typing import Protocol

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client.models import SparseVector


class EmbeddingError(RuntimeError):
    """Raised when an embedding model fails or returns an unexpected shape."""


class EmbeddingProvider(Protocol):
    dimension: int

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class SparseEmbeddingProvider(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[SparseVector]: ...

    async def embed_query(self, text: str) -> SparseVector: ...


class _AsyncFastEmbedBase:
    def __init__(
        self,
        model_name: str,
        *,
        cache_dir: str | None = None,
        batch_size: int = 32,
        timeout_seconds: float = 120.0,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.batch_size = batch_size
        self.timeout_seconds = timeout_seconds
        self._model: object | None = None
        self._model_lock = threading.Lock()
        self._async_lock = asyncio.Lock()

    def _build_model(self) -> object:
        raise NotImplementedError

    def _embed_sync(self, texts: list[str], *, query: bool) -> list[object]:
        raise NotImplementedError

    def _load_model(self) -> object:
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    self._model = self._build_model()
        return self._model

    async def _run(self, texts: list[str], *, query: bool) -> list[object]:
        if not texts:
            return []
        async with self._async_lock:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(self._load_and_embed, texts, query),
                    timeout=self.timeout_seconds,
                )
            except TimeoutError as exc:
                raise EmbeddingError(
                    f"embedding model {self.model_name} timed out after "
                    f"{self.timeout_seconds:g}s"
                ) from exc

    def _load_and_embed(self, texts: list[str], query: bool) -> list[object]:
        self._load_model()
        return self._embed_sync(texts, query=query)

    def _batches(self, texts: list[str]) -> list[list[str]]:
        return [
            texts[start : start + self.batch_size]
            for start in range(0, len(texts), self.batch_size)
        ]


class FastEmbedDenseProvider(_AsyncFastEmbedBase):
    def __init__(
        self,
        model_name: str,
        dimension: int,
        *,
        cache_dir: str | None = None,
        batch_size: int = 32,
        timeout_seconds: float = 120.0,
    ) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        super().__init__(
            model_name,
            cache_dir=cache_dir,
            batch_size=batch_size,
            timeout_seconds=timeout_seconds,
        )
        self.dimension = dimension

    def _build_model(self) -> object:
        return TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)

    def _embed_sync(self, texts: list[str], *, query: bool) -> list[object]:
        model = self._model
        assert model is not None
        vectors: list[list[float]] = []
        for batch in self._batches(texts):
            embeddings = (
                model.query_embed(batch) if query else model.embed(batch, batch_size=len(batch))
            )
            for embedding in embeddings:
                vector = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
                if len(vector) != self.dimension:
                    raise EmbeddingError(
                        f"model {self.model_name} produced {len(vector)} dimensions, "
                        f"expected EMBEDDING_DIM={self.dimension}"
                    )
                vectors.append([float(value) for value in vector])
        return vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._run(list(texts), query=False)

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._run([text], query=True)
        return vectors[0]


class FastEmbedSparseProvider(_AsyncFastEmbedBase):
    def __init__(
        self,
        model_name: str = "Qdrant/bm25",
        *,
        cache_dir: str | None = None,
        batch_size: int = 32,
        timeout_seconds: float = 120.0,
    ) -> None:
        super().__init__(
            model_name,
            cache_dir=cache_dir,
            batch_size=batch_size,
            timeout_seconds=timeout_seconds,
        )

    def _build_model(self) -> object:
        return SparseTextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)

    def _embed_sync(self, texts: list[str], *, query: bool) -> list[SparseVector]:
        model = self._model
        assert model is not None
        vectors: list[SparseVector] = []
        for batch in self._batches(texts):
            embeddings = model.query_embed(batch) if query else model.embed(batch)
            for embedding in embeddings:
                if len(embedding.indices) != len(embedding.values):
                    raise EmbeddingError(
                        f"model {self.model_name} returned mismatched sparse indices/values"
                    )
                vectors.append(
                    SparseVector(
                        indices=[int(index) for index in embedding.indices],
                        values=[float(value) for value in embedding.values],
                    )
                )
        return vectors

    async def embed_documents(self, texts: list[str]) -> list[SparseVector]:
        return await self._run(list(texts), query=False)

    async def embed_query(self, text: str) -> SparseVector:
        vectors = await self._run([text], query=True)
        vector = vectors[0]
        if not vector.indices:
            raise EmbeddingError("query produced an empty sparse vector")
        return vector
