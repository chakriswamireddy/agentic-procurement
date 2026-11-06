from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AbstentionReason = Literal["no_matching_policy", "weak_evidence"]


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: str
    document_id: str
    version: str
    title: str
    section_path: str
    text: str
    score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
    source_path: str
    effective_from: date
    effective_to: date | None = None
    injection_suspected: bool = False
    status: str | None = None
    classification: str | None = None


class PolicySearchResponse(BaseModel):
    query: str
    inconclusive: bool
    reason: AbstentionReason | None = None
    evidence: list[EvidenceRead] = Field(default_factory=list)
