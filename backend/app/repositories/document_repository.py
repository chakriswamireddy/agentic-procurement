from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres.models import PolicyDocument
from app.schemas.document import IngestionStatus, PolicyDocumentRecord


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_document(self, doc: PolicyDocumentRecord) -> None:
        values = doc.model_dump(exclude={"created_at"})
        statement = pg_insert(PolicyDocument).values(**values)
        update_columns = {
            column: getattr(statement.excluded, column)
            for column in values
            if column not in {"id", "version"}
        }
        statement = statement.on_conflict_do_update(
            index_elements=[PolicyDocument.id, PolicyDocument.version],
            set_=update_columns,
        )
        await self.session.execute(statement)
        await self.session.commit()

    async def get_document(
        self,
        document_id: str,
        version: str | None = None,
    ) -> PolicyDocumentRecord | None:
        statement = select(PolicyDocument).where(PolicyDocument.id == document_id)
        if version is not None:
            statement = statement.where(PolicyDocument.version == version)
        statement = statement.order_by(
            PolicyDocument.effective_from.desc(),
            PolicyDocument.created_at.desc(),
        ).limit(1)
        row = (await self.session.execute(statement)).scalar_one_or_none()
        return PolicyDocumentRecord.model_validate(row) if row is not None else None

    async def list_documents(self, status: str | None = None) -> list[PolicyDocumentRecord]:
        statement = select(PolicyDocument).order_by(PolicyDocument.id, PolicyDocument.version)
        if status is not None:
            statement = statement.where(PolicyDocument.status == status)
        rows = (await self.session.execute(statement)).scalars().all()
        return [PolicyDocumentRecord.model_validate(row) for row in rows]

    async def set_ingestion_status(
        self,
        document_id: str,
        version: str,
        status: IngestionStatus,
        *,
        chunk_count: int = 0,
        error: str | None = None,
    ) -> None:
        values: dict[str, object] = {
            "ingestion_status": status,
            "ingestion_error": error,
            "chunk_count": chunk_count,
        }
        if status == "ingested":
            values["ingested_at"] = func.now()
        else:
            values["ingested_at"] = None

        statement = (
            update(PolicyDocument)
            .where(
                PolicyDocument.id == document_id,
                PolicyDocument.version == version,
            )
            .values(**values)
        )
        result = await self.session.execute(statement)
        if result.rowcount == 0:
            raise LookupError(
                f"policy document {document_id} version {version} is not registered"
            )
        await self.session.commit()
