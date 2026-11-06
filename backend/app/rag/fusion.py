"""Reciprocal rank fusion for dense and sparse retrieval results."""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

RRF_K = 60


@dataclass(frozen=True)
class RankedHit:
    chunk_id: str
    score: float
    payload: dict[str, Any]


@dataclass(frozen=True)
class FusedHit:
    chunk_id: str
    score: float
    payload: dict[str, Any]
    dense_rank: int | None = None
    sparse_rank: int | None = None
    dense_score: float | None = None
    sparse_score: float | None = None


def reciprocal_rank_fusion(
    *result_lists: list[RankedHit],
    k: int = RRF_K,
) -> list[FusedHit]:
    """Fuse ranked lists with ``sum(1 / (k + rank))``.

    Ranks start at 1. Raw retrieval scores are deliberately ignored because
    cosine similarity and BM25 scores are not comparable. Ties break on
    ``chunk_id`` so output is deterministic.
    """
    if k <= 0:
        raise ValueError("k must be positive")

    scores: dict[str, float] = defaultdict(float)
    payloads: dict[str, dict[str, Any]] = {}
    dense_ranks: dict[str, int] = {}
    sparse_ranks: dict[str, int] = {}
    dense_scores: dict[str, float] = {}
    sparse_scores: dict[str, float] = {}

    for list_index, results in enumerate(result_lists):
        seen: set[str] = set()
        for rank, hit in enumerate(results, start=1):
            if hit.chunk_id in seen:
                continue
            seen.add(hit.chunk_id)
            scores[hit.chunk_id] += 1.0 / (k + rank)
            payloads.setdefault(hit.chunk_id, hit.payload)
            if list_index == 0:
                dense_ranks[hit.chunk_id] = rank
                dense_scores[hit.chunk_id] = hit.score
            elif list_index == 1:
                sparse_ranks[hit.chunk_id] = rank
                sparse_scores[hit.chunk_id] = hit.score

    fused = [
        FusedHit(
            chunk_id=chunk_id,
            score=score,
            payload=payloads[chunk_id],
            dense_rank=dense_ranks.get(chunk_id),
            sparse_rank=sparse_ranks.get(chunk_id),
            dense_score=dense_scores.get(chunk_id),
            sparse_score=sparse_scores.get(chunk_id),
        )
        for chunk_id, score in scores.items()
    ]
    fused.sort(key=lambda hit: (-hit.score, hit.chunk_id))
    return fused
