from app.rag.abstention import NO_MATCHING_POLICY, WEAK_EVIDENCE, assess_evidence
from app.rag.fusion import FusedHit


def hit(
    *,
    text: str = "The approval threshold for laptops is INR 50000.",
    dense_score: float | None = 0.8,
    sparse_score: float | None = 3.0,
) -> FusedHit:
    return FusedHit(
        chunk_id="chunk-1",
        score=0.032,
        payload={"text": text},
        dense_score=dense_score,
        sparse_score=sparse_score,
    )


def assess(hits, *, min_dense=0.60, min_sparse=2.0, min_text=40):
    return assess_evidence(
        hits,
        min_dense_score=min_dense,
        min_sparse_score=min_sparse,
        min_text_chars=min_text,
    )


def test_no_results_abstains() -> None:
    decision = assess([])

    assert decision.inconclusive is True
    assert decision.reason == NO_MATCHING_POLICY


def test_weak_scores_abstain() -> None:
    decision = assess([hit(dense_score=0.45, sparse_score=1.2)])

    assert decision.inconclusive is True
    assert decision.reason == WEAK_EVIDENCE


def test_strong_dense_evidence_passes() -> None:
    decision = assess([hit(dense_score=0.82, sparse_score=None)])

    assert decision.inconclusive is False
    assert decision.reason is None


def test_strong_sparse_evidence_passes() -> None:
    decision = assess([hit(dense_score=None, sparse_score=6.0)])

    assert decision.inconclusive is False


def test_short_text_abstains() -> None:
    decision = assess([hit(text="[Section: 1] short", dense_score=0.9)])

    assert decision.inconclusive is True
    assert decision.reason == WEAK_EVIDENCE