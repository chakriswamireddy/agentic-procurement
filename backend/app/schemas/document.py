from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

DocumentStatus = Literal["active", "obsolete", "draft"]
DocumentClassification = Literal["public", "internal", "restricted"]
IngestionStatus = Literal["registered", "ingesting", "ingested", "failed"]


class PolicyDocumentRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: str
    title: str
    status: DocumentStatus
    classification: DocumentClassification
    effective_from: date
    effective_to: date | None = None
    source_path: str
    checksum: str
    chunk_count: int = 0
    ingestion_status: IngestionStatus = "registered"
    ingestion_error: str | None = None
    ingested_at: datetime | None = None
    created_at: datetime | None = None


class PolicyDocumentList(BaseModel):
    items: list[PolicyDocumentRecord]
    total: int
