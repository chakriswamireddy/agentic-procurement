import os
import tempfile
from pathlib import Path

from qdrant_client.http.exceptions import (
    ApiException,
    ResponseHandlingException,
    UnexpectedResponse,
)

from app.core.config import REPO_ROOT, Settings
from app.core.errors import (
    ConflictError,
    DependencyUnavailableError,
    IngestionFailedError,
    NotFoundError,
    ValidationError,
)
from app.rag.document_loader import (
    MAX_FILE_SIZE_BYTES,
    DocumentValidationError,
    LoadedDocument,
    load_document,
)
from app.rag.embeddings import EmbeddingError
from app.rag.indexer import IndexingError, PolicyIndexer
from app.rag.runtime import get_embedding_providers, get_qdrant_client
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import PolicyDocumentRecord

DOCUMENTS_DIR = REPO_ROOT / "data" / "documents"


class DocumentService:
    def __init__(
        self,
        documents: DocumentRepository,
        settings: Settings,
        *,
        documents_dir: Path | None = None,
        indexer: PolicyIndexer | None = None,
    ) -> None:
        self.documents = documents
        self.settings = settings
        self.documents_dir = documents_dir or DOCUMENTS_DIR
        self._indexer = indexer

    @staticmethod
    def _validation_error(exc: DocumentValidationError) -> ValidationError:
        return ValidationError(
            str(exc),
            details={"file": exc.path.name, "field": exc.field},
        )

    def _indexer_for(self) -> PolicyIndexer:
        if self._indexer is not None:
            return self._indexer
        dense, sparse = get_embedding_providers(self.settings)
        return PolicyIndexer(
            get_qdrant_client(self.settings),
            dense,
            sparse,
            self.documents,
            collection_name=self.settings.qdrant_collection,
            embedding_model=self.settings.embedding_model,
        )

    async def upload(self, filename: str, content: bytes) -> PolicyDocumentRecord:
        if Path(filename).suffix.lower() != ".md":
            raise ValidationError(
                "only .md documents are supported",
                details={"file": Path(filename).name, "field": "file"},
            )
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise ValidationError(
                f"file exceeds maximum size of {MAX_FILE_SIZE_BYTES} bytes",
                details={"file": Path(filename).name, "field": "file"},
            )

        self.documents_dir.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.documents_dir, suffix=".md", delete=False
            ) as temporary:
                temporary.write(content)
                temp_path = Path(temporary.name)

            loaded = load_document(temp_path)
            target = self._target_path(loaded)
            if target.exists():
                existing = load_document(target)
                if existing.checksum != loaded.checksum:
                    raise ConflictError(
                        f"{loaded.document_id} version {loaded.version} already exists "
                        "with different content"
                    )
                temp_path.unlink()
                temp_path = None
            else:
                os.replace(temp_path, target)
                temp_path = None

            registered = load_document(target)
        except DocumentValidationError as exc:
            raise self._validation_error(exc) from exc
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

        await self.documents.upsert_document(
            self._record(registered, ingestion_status="registered")
        )
        record = await self.documents.get_document(registered.document_id, registered.version)
        if record is None:
            raise IngestionFailedError("document registration failed")
        return record

    def _target_path(self, document: LoadedDocument) -> Path:
        safe_version = "".join(
            character if character.isalnum() or character in {".", "-"} else "-"
            for character in document.version
        )
        return self.documents_dir / f"{document.document_id.lower()}-v{safe_version}.md"

    @staticmethod
    def _record(
        document: LoadedDocument,
        *,
        ingestion_status: str = "registered",
    ) -> PolicyDocumentRecord:
        return PolicyDocumentRecord(
            id=document.document_id,
            version=document.version,
            title=document.title,
            status=document.status,  # type: ignore[arg-type]
            classification=document.classification,  # type: ignore[arg-type]
            effective_from=document.effective_from,
            effective_to=document.effective_to,
            source_path=document.source_path,
            checksum=document.checksum,
            ingestion_status=ingestion_status,  # type: ignore[arg-type]
            chunk_count=0,
        )

    async def list_documents(self, status: str | None = None) -> list[PolicyDocumentRecord]:
        return await self.documents.list_documents(status)

    async def get_document(
        self,
        document_id: str,
        version: str | None = None,
    ) -> PolicyDocumentRecord:
        record = await self.documents.get_document(document_id, version)
        if record is None:
            suffix = f" version {version}" if version else ""
            raise NotFoundError(f"document {document_id}{suffix} not found")
        return record

    async def ingest(self, document_id: str, version: str | None = None) -> PolicyDocumentRecord:
        record = await self.get_document(document_id, version)
        source = (REPO_ROOT / record.source_path).resolve()
        if REPO_ROOT.resolve() not in source.parents:
            raise ValidationError("document source path is outside the repository")
        if not source.is_file():
            raise NotFoundError(f"source file for {document_id} is missing")

        try:
            loaded = load_document(source)
        except DocumentValidationError as exc:
            raise self._validation_error(exc) from exc

        if (loaded.document_id, loaded.version) != (record.id, record.version):
            raise ConflictError("source file identity does not match the registry record")

        try:
            await self._indexer_for().index_document(loaded)
        except (
            EmbeddingError,
            ApiException,
            ResponseHandlingException,
            UnexpectedResponse,
            OSError,
            TimeoutError,
            ConnectionError,
        ) as exc:
            raise DependencyUnavailableError("document ingestion unavailable") from exc
        except IndexingError as exc:
            raise IngestionFailedError(str(exc)) from exc

        updated = await self.documents.get_document(document_id, record.version)
        if updated is None:
            raise IngestionFailedError("document record disappeared after ingestion")
        return updated
