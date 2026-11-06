# 0005 — Retrieval abstention thresholds

- **Date:** 2026-11-04
- **Status:** accepted
- **Context:** Phase 2 needs an abstention path. A fused RRF score is not a
  relevance measure: with `k=60` and `candidate_k=20`, any single-list hit scores at
  least `1 / (60 + 20) = 0.0125`, so a fused-score threshold cannot separate relevant
  from irrelevant results. The retriever therefore preserves the raw dense and sparse
  scores on each fused hit, and abstention uses those raw scores.

## Decision

Abstain when either condition holds:

1. No hits survive the metadata filters → `inconclusive: true`,
   `reason: "no_matching_policy"`.
2. Both relevance signals are weak → `inconclusive: true`,
   `reason: "weak_evidence"`:
   - top raw dense cosine `< RETRIEVAL_MIN_DENSE_SCORE` (default `0.60`), and
   - top raw sparse BM25 `< RETRIEVAL_MIN_SPARSE_SCORE` (default `2.0`).
3. All returned chunk texts are shorter than `RETRIEVAL_MIN_TEXT_CHARS` (default `40`)
   after removing the `[Section: ...]` prefix.

The comparison is an OR for passing: a strong sparse exact-term match can rescue a
weaker dense score, and vice versa. This matters for identifiers such as `ISO14001`,
where dense similarity is only about `0.63` but sparse retrieval is precise.

## Calibration data

Measured against the ingested 226-chunk index on 2026-11-04:

| Query | Top dense | Top sparse | Desired |
|---|---:|---:|---|
| approval threshold for laptop purchases | 0.838 | 7.15 | answer |
| Who approves a purchase of 500 laptops? | 0.828 | 7.21 | answer |
| What is the warranty for laptops? | 0.796 | 3.59 | answer |
| emergency procurement value limit | 0.843 | 6.92 | answer |
| ISO14001 | 0.632 | 1.59 | answer (sparse exact term) |
| What is the capital of France? | 0.445 | none | abstain |
| How do I bake sourdough bread at home? | 0.434 | none | abstain |
| zzzz unrelated zzzz | 0.539 | 1.59 | abstain |

Off-domain dense scores stayed at or below `0.54`; policy-relevant dense scores were at
least `0.63`. The dense threshold of `0.60` sits in that gap. Off-domain sparse scores
were absent or at most `1.59`; policy-relevant sparse scores were at least `3.5`, except
for the exact identifier query, which is handled by its dense score.

## Evaluation result

`scripts/evaluate_retrieval.py` on the 20-case set (`k=5`):

| Mode | Recall@5 | MRR@5 | Context precision@5 | Abstention accuracy | False abstention | Version leaks |
|---|---:|---:|---:|---:|---:|---:|
| dense | 0.944 | 0.810 | 0.356 | 1.000 | 0.000 | 0.000 |
| sparse | 0.944 | 0.944 | 0.311 | 1.000 | 0.000 | 0.000 |
| hybrid | 1.000 | 0.883 | 0.322 | 1.000 | 0.000 | 0.000 |

Hybrid wins on recall, which is the Phase 2 target. Sparse has the best MRR because
policy questions often contain exact terms; hybrid retains that strength while covering
paraphrases.

## Consequences

- Thresholds are configuration, not constants: changing the embedding model, chunker, or
  document set requires recalibration with the evaluation script.
- Raw scores are retained for diagnostics only. Fusion still uses ranks, never a sum of
  incomparable dense and sparse scores.
- The evaluation script fails when hybrid recall@5 drops below `0.8` or any obsolete or
  draft result leaks into default retrieval.
