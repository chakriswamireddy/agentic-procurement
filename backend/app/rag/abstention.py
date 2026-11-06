"""Abstention rules for weak or missing policy evidence."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.rag.fusion import FusedHit

NO_MATCHING_POLICY = "no_matching_policy"
WEAK_EVIDENCE = "weak_evidence"
_SECTION_PREFIX = re.compile(r"^\[Section:[^\]]*\]\s*")


@dataclass(frozen=True)
class AbstentionDecision:
    inconclusive: bool
    reason: str | None = None


def evidence_text(text: str) -> str:
    return _SECTION_PREFIX.sub("", text).strip()


def assess_evidence(
    hits: Sequence[FusedHit],
    *,
    min_dense_score: float,
    min_sparse_score: float,
    min_text_chars: int,
) -> AbstentionDecision:
    if not hits:
        return AbstentionDecision(True, NO_MATCHING_POLICY)

    top_dense = max(
        (hit.dense_score for hit in hits if hit.dense_score is not None),
        default=None,
    )
    top_sparse = max(
        (hit.sparse_score for hit in hits if hit.sparse_score is not None),
        default=None,
    )
    dense_weak = top_dense is None or top_dense < min_dense_score
    sparse_weak = top_sparse is None or top_sparse < min_sparse_score
    if dense_weak and sparse_weak:
        return AbstentionDecision(True, WEAK_EVIDENCE)

    texts = [
        evidence_text(str(hit.payload.get("text", "")))
        for hit in hits
        if hit.payload.get("text")
    ]
    if not texts or all(len(text) < min_text_chars for text in texts):
        return AbstentionDecision(True, WEAK_EVIDENCE)

    return AbstentionDecision(False, None)
