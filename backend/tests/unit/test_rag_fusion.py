import pytest
from app.rag.fusion import RankedHit, reciprocal_rank_fusion


def hit(chunk_id: str, score: float = 0.0) -> RankedHit:
    return RankedHit(chunk_id=chunk_id, score=score, payload={"chunk_id": chunk_id})


def test_rrf_uses_ranks_and_expected_order() -> None:
    dense = [hit("A"), hit("B"), hit("C")]
    sparse = [hit("C"), hit("B"), hit("D")]

    fused = reciprocal_rank_fusion(dense, sparse, k=60)

    assert [item.chunk_id for item in fused] == ["C", "B", "A", "D"]
    assert fused[0].dense_rank == 3
    assert fused[0].sparse_rank == 1
    assert fused[1].dense_rank == 2
    assert fused[1].sparse_rank == 2


def test_rrf_scores_follow_formula() -> None:
    fused = reciprocal_rank_fusion([hit("A")], [hit("A")], k=60)

    assert fused[0].score == pytest.approx(2 / 61)


def test_rrf_ignores_raw_scores() -> None:
    dense = [hit("A", score=1000.0)]
    sparse = [hit("B", score=1.0)]

    fused = reciprocal_rank_fusion(dense, sparse, k=60)

    assert fused[0].score == fused[1].score
    assert [item.chunk_id for item in fused] == ["A", "B"]


def test_rrf_ties_break_deterministically_by_chunk_id() -> None:
    fused = reciprocal_rank_fusion([hit("Y")], [hit("X")], k=60)

    assert [item.chunk_id for item in fused] == ["X", "Y"]


def test_rrf_does_not_double_count_duplicate_in_one_list() -> None:
    fused = reciprocal_rank_fusion([hit("A"), hit("A")], k=60)

    assert len(fused) == 1
    assert fused[0].score == pytest.approx(1 / 61)


def test_rrf_rejects_invalid_k() -> None:
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([hit("A")], k=0)
