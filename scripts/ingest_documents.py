import argparse
import asyncio
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

import psycopg
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from app.rag.chunker import chunk_document  # noqa: E402
from app.rag.document_loader import LoadedDocument, load_documents  # noqa: E402
from app.rag.embeddings import (  # noqa: E402
    FastEmbedDenseProvider,
    FastEmbedSparseProvider,
)
from app.rag.indexer import PolicyIndexer, ensure_collection  # noqa: E402
from app.repositories.document_repository import DocumentRepository  # noqa: E402

DOCUMENTS_DIR = ROOT / "data" / "documents"
SCHEMA_DIR = ROOT / "scripts" / "sql"
URL_KEYS = ("DATABASE_URL", "QDRANT_URL")
SECRET_MARKERS = ("PASSWORD", "SECRET", "TOKEN", "API_KEY", "APIKEY")


def strip_driver(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme.split("+", 1)[0]
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


def redact(message: str) -> str:
    for key in URL_KEYS:
        value = os.getenv(key)
        if value:
            message = message.replace(value, "<redacted-url>")

    secrets = []
    for key, value in os.environ.items():
        upper_key = key.upper()
        if not value:
            continue
        if any(marker in upper_key for marker in SECRET_MARKERS):
            secrets.append(value)
        if upper_key in URL_KEYS:
            try:
                password = urlsplit(value).password
            except ValueError:
                password = None
            if password:
                secrets.append(password)
                secrets.append(unquote(password))

    for secret in sorted(set(secrets), key=len, reverse=True):
        if len(secret) >= 4:
            message = message.replace(secret, "***")

    message = re.sub(
        r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key)=([^&\s,;]+)",
        r"\1=***",
        message,
    )
    return re.sub(r"://[^/@\s]+@", "://***@", message)


def error_text(exc: BaseException) -> str:
    return " ".join(str(exc).split()) or exc.__class__.__name__


def apply_schema(database_url: str) -> None:
    schema_files = sorted(SCHEMA_DIR.glob("*.sql"))
    if not schema_files:
        raise RuntimeError(f"no schema files found in {SCHEMA_DIR}")
    with psycopg.connect(strip_driver(database_url), autocommit=True) as connection:
        for schema_path in schema_files:
            connection.execute(schema_path.read_text(encoding="utf-8"))


def select_documents(
    documents: list[LoadedDocument],
    *,
    document_id: str | None,
    version: str | None,
) -> list[LoadedDocument]:
    selected = documents
    if document_id:
        selected = [doc for doc in selected if doc.document_id == document_id]
    if version:
        selected = [doc for doc in selected if doc.version == version]
    return selected


def print_row(
    document: LoadedDocument,
    *,
    status: str,
    chunks: int,
    tokens: int,
    duration: float,
) -> None:
    print(
        f"{document.document_id:<10} {document.version:<8} {document.status:<9} "
        f"{chunks:>6} {tokens:>7} {duration:>8.2f}s  {status}"
    )


def dry_run(documents: list[LoadedDocument]) -> int:
    failures = 0
    print(
        f"{'document':<10} {'version':<8} {'status':<9} "
        f"{'chunks':>6} {'tokens':>7} {'duration':>9}  result"
    )
    for document in documents:
        started = time.perf_counter()
        try:
            chunks = chunk_document(document)
            tokens = sum(chunk.token_count for chunk in chunks)
        except Exception as exc:
            failures += 1
            print(
                f"{document.document_id:<10} {document.version:<8} "
                f"{document.status:<9} {'-':>6} {'-':>7} "
                f"{time.perf_counter() - started:>8.2f}s  failed: "
                f"{redact(error_text(exc))}",
                file=sys.stderr,
            )
            continue
        print_row(
            document,
            status="dry-run",
            chunks=len(chunks),
            tokens=tokens,
            duration=time.perf_counter() - started,
        )
    return 1 if failures else 0


async def ingest(
    settings: Settings,
    documents: list[LoadedDocument],
    *,
    rebuild: bool,
) -> int:
    apply_schema(settings.database_url)

    engine = create_async_engine(settings.database_url, pool_size=2, max_overflow=2)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
    )
    dense = FastEmbedDenseProvider(
        settings.embedding_model,
        settings.embedding_dim,
        cache_dir=settings.fastembed_cache_dir or None,
        batch_size=settings.embedding_batch_size,
        timeout_seconds=settings.embedding_timeout_seconds,
    )
    sparse = FastEmbedSparseProvider(
        settings.sparse_embedding_model,
        cache_dir=settings.fastembed_cache_dir or None,
        batch_size=settings.embedding_batch_size,
        timeout_seconds=settings.embedding_timeout_seconds,
    )

    failures = 0
    print(
        f"{'document':<10} {'version':<8} {'status':<9} "
        f"{'chunks':>6} {'tokens':>7} {'duration':>9}  result"
    )
    try:
        await ensure_collection(
            client,
            settings.qdrant_collection,
            settings.embedding_dim,
            recreate=rebuild,
        )

        async with session_factory() as session:
            indexer = PolicyIndexer(
                client,
                dense,
                sparse,
                DocumentRepository(session),
                collection_name=settings.qdrant_collection,
                embedding_model=settings.embedding_model,
            )
            for document in documents:
                started = time.perf_counter()
                try:
                    chunk_count = await indexer.index_document(document)
                    chunks = chunk_document(document)
                    token_count = sum(chunk.token_count for chunk in chunks)
                except Exception as exc:
                    failures += 1
                    print(
                        f"{document.document_id:<10} {document.version:<8} "
                        f"{document.status:<9} {'-':>6} {'-':>7} "
                        f"{time.perf_counter() - started:>8.2f}s  failed: "
                        f"{redact(error_text(exc))}",
                        file=sys.stderr,
                    )
                else:
                    print_row(
                        document,
                        status="ingested",
                        chunks=chunk_count,
                        tokens=token_count,
                        duration=time.perf_counter() - started,
                    )
    finally:
        await client.close()
        await engine.dispose()

    if failures:
        print(
            f"document ingestion completed with {failures} failure(s)",
            file=sys.stderr,
        )
        return 1
    print(f"ingested {len(documents)} documents into {settings.qdrant_collection}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest policy documents into Qdrant.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="ingest every document (default when --document-id is omitted)",
    )
    parser.add_argument("--document-id", help="ingest only this document ID")
    parser.add_argument("--version", help="ingest only this document version")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and chunk without writing to PostgreSQL or Qdrant",
    )
    parser.add_argument(
        "--rebuild",
        "--recreate",
        dest="rebuild",
        action="store_true",
        help="delete and recreate the collection, then re-ingest the selection",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm the destructive --rebuild operation",
    )
    args = parser.parse_args()

    if args.version and not args.document_id:
        parser.error("--version requires --document-id")
    if args.rebuild and not args.yes:
        parser.error("--rebuild requires --yes")

    try:
        documents = load_documents(DOCUMENTS_DIR)
        if not documents:
            raise RuntimeError(f"no Markdown documents found in {DOCUMENTS_DIR}")
        selected = select_documents(
            documents,
            document_id=args.document_id,
            version=args.version,
        )
        if not selected:
            raise RuntimeError(
                f"no documents matched document_id={args.document_id!r} "
                f"version={args.version!r}"
            )
        if args.dry_run:
            return dry_run(selected)
        return asyncio.run(
            ingest(Settings(), selected, rebuild=args.rebuild)
        )
    except Exception as exc:
        print(f"document ingestion failed: {redact(error_text(exc))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
