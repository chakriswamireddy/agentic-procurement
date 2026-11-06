"""Reproducible Qdrant collection setup and idempotent policy indexing."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointIdsList,
    PointStruct,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

from app.rag.chunker import Chunk, chunk_document
from app.rag.document_loader import LoadedDocument
from app.rag.embeddings import EmbeddingProvider, SparseEmbeddingProvider
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import PolicyDocumentRecord

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
UPSERT_BATCH_SIZE = 64
PAYLOAD_INDEXES: dict[str, PayloadSchemaType] = {
    "document_id": PayloadSchemaType.KEYWORD,
    "version": PayloadSchemaType.KEYWORD,
    "status": PayloadSchemaType.KEYWORD,
    "classification": PayloadSchemaType.KEYWORD,
    "effective_from": PayloadSchemaType.DATETIME,
    "effective_to": PayloadSchemaType.DATETIME,
}


class IndexSchemaError(RuntimeError):
    """Raised when an existing collection does not match the expected schema."""


class IndexingError(RuntimeError):
    """Raised when a document cannot be indexed."""


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def _date_value(value: date | None) -> str | None:
    return f"{value.isoformat()}T00:00:00Z" if value is not None else None


def _dense_size(vectors: Any) -> int | None:
    if isinstance(vectors, dict):
        dense = vectors.get(DENSE_VECTOR_NAME)
        return getattr(dense, "size", None)
    return getattr(vectors, "size", None)


async def ensure_collection(
    client: AsyncQdrantClient,
    collection_name: str,
    dimension: int,
    *,
    recreate: bool = False,
) -> None:
    if dimension <= 0:
        raise IndexSchemaError("EMBEDDING_DIM must be positive")

    exists = await client.collection_exists(collection_name)
    if exists and recreate:
        await client.delete_collection(collection_name)
        exists = False

    if not exists:
        await client.create_collection(
            collection_name=collection_name,
            vectors_config={
                DENSE_VECTOR_NAME: VectorParams(size=dimension, distance=Distance.COSINE)
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: SparseVectorParams(
                    index=SparseIndexParams(on_disk=False)
                )
            },
        )
    else:
        info = await client.get_collection(collection_name)
        size = _dense_size(info.config.params.vectors)
        if size != dimension:
            raise IndexSchemaError(
                f"collection {collection_name} has dense vector size {size}, "
                f"expected {dimension}; use --recreate or fix EMBEDDING_DIM"
            )
        sparse_vectors = info.config.params.sparse_vectors or {}
        if SPARSE_VECTOR_NAME not in sparse_vectors:
            raise IndexSchemaError(
                f"collection {collection_name} is missing the {SPARSE_VECTOR_NAME!r} "
                "sparse vector; use --recreate to rebuild it"
            )

    info = await client.get_collection(collection_name)
    existing_indexes = set((info.payload_schema or {}).keys())
    for field_name, field_schema in PAYLOAD_INDEXES.items():
        if field_name in existing_indexes:
            continue
        await client.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema=field_schema,
        )


class PolicyIndexer:
    def __init__(
        self,
        client: AsyncQdrantClient,
        dense: EmbeddingProvider,
        sparse: SparseEmbeddingProvider,
        documents: DocumentRepository,
        *,
        collection_name: str,
        embedding_model: str,
    ) -> None:
        self.client = client
        self.dense = dense
        self.sparse = sparse
        self.documents = documents
        self.collection_name = collection_name
        self.embedding_model = embedding_model

    def _payload(self, chunk: Chunk, doc: LoadedDocument, ingested_at: str) -> dict[str, Any]:
        return {
            "chunk_id": chunk.chunk_id,
            "document_id": doc.document_id,
            "version": doc.version,
            "title": doc.title,
            "status": doc.status,
            "classification": doc.classification,
            "effective_from": _date_value(doc.effective_from),
            "effective_to": _date_value(doc.effective_to),
            "section_path": chunk.section_path,
            "chunk_index": chunk.chunk_index,
            "source_path": doc.source_path,
            "checksum": doc.checksum,
            "text": chunk.text,
            "embedding_model": self.embedding_model,
            "ingested_at": ingested_at,
        }

    async def _existing_point_ids(self, document_id: str, version: str) -> set[str]:
        point_ids: set[str] = set()
        offset: Any = None
        scroll_filter = Filter(
            must=[
                FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                FieldCondition(key="version", match=MatchValue(value=version)),
            ]
        )
        while True:
            points, offset = await self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=scroll_filter,
                limit=256,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            point_ids.update(str(point.id) for point in points)
            if offset is None:
                break
        return point_ids

    async def _count_points(self, document_id: str, version: str) -> int:
        result = await self.client.count(
            collection_name=self.collection_name,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id", match=MatchValue(value=document_id)
                    ),
                    FieldCondition(key="version", match=MatchValue(value=version)),
                ]
            ),
            exact=True,
        )
        return result.count

    @staticmethod
    def _safe_error(exc: BaseException) -> str:
        message = " ".join(str(exc).split()) or exc.__class__.__name__
        return message[:500]

    async def index_document(self, doc: LoadedDocument) -> int:
        await self.documents.upsert_document(
            PolicyDocumentRecord(
                id=doc.document_id,
                version=doc.version,
                title=doc.title,
                status=doc.status,  # type: ignore[arg-type]
                classification=doc.classification,  # type: ignore[arg-type]
                effective_from=doc.effective_from,
                effective_to=doc.effective_to,
                source_path=doc.source_path,
                checksum=doc.checksum,
                ingestion_status="ingesting",
                chunk_count=0,
            )
        )

        try:
            chunks = chunk_document(doc)
            if not chunks:
                raise IndexingError(
                    f"{doc.document_id} version {doc.version} produced no chunks"
                )

            texts = [chunk.text for chunk in chunks]
            dense_vectors = await self.dense.embed_documents(texts)
            sparse_vectors = await self.sparse.embed_documents(texts)
            if len(dense_vectors) != len(chunks) or len(sparse_vectors) != len(chunks):
                raise IndexingError("embedding count does not match chunk count")

            existing_ids = await self._existing_point_ids(doc.document_id, doc.version)
            ingested_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            points = [
                PointStruct(
                    id=_point_id(chunk.chunk_id),
                    vector={
                        DENSE_VECTOR_NAME: dense_vector,
                        SPARSE_VECTOR_NAME: sparse_vector,
                    },
                    payload=self._payload(chunk, doc, ingested_at),
                )
                for chunk, dense_vector, sparse_vector in zip(
                    chunks, dense_vectors, sparse_vectors, strict=True
                )
            ]

            for start in range(0, len(points), UPSERT_BATCH_SIZE):
                await self.client.upsert(
                    collection_name=self.collection_name,
                    points=points[start : start + UPSERT_BATCH_SIZE],
                    wait=True,
                )

            stale_ids = existing_ids - {str(point.id) for point in points}
            if stale_ids:
                await self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=PointIdsList(points=sorted(stale_ids)),
                    wait=True,
                )

            count = await self._count_points(doc.document_id, doc.version)
            if count != len(chunks):
                raise IndexingError(
                    f"indexed point count {count} does not match chunk count {len(chunks)}"
                )

            await self.documents.set_ingestion_status(
                doc.document_id,
                doc.version,
                "ingested",
                chunk_count=len(chunks),
            )
            return len(chunks)
        except Exception as exc:
            await self.documents.set_ingestion_status(
                doc.document_id,
                doc.version,
                "failed",
                chunk_count=0,
                error=self._safe_error(exc),
            )
            raise

    async def delete_document_version(self, document_id: str, version: str) -> None:
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id", match=MatchValue(value=document_id)
                    ),
                    FieldCondition(key="version", match=MatchValue(value=version)),
                ]
            ),
            wait=True,
        )
