import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from app.rag.abstention import assess_evidence  # noqa: E402
from app.rag.fusion import FusedHit  # noqa: E402
from app.rag.retriever import RetrievalFilters  # noqa: E402
from app.rag.runtime import build_retriever  # noqa: E402

QUESTIONS = ROOT / "data" / "evaluation" / "rag_questions.json"
RESULTS_DIR = ROOT / "data" / "evaluation"
MODES = ("dense", "sparse", "hybrid")
LEAKED_STATUSES = frozenset({"obsolete", "draft"})


@dataclass
class CaseResult:
    case_id: str
    mode: str
    category: str
    top_documents: list[str]
    relevant_rank: int | None
    recall: bool
    reciprocal_rank: float
    context_precision: float
    abstained: bool
    abstention_reason: str | None
    expected_abstention: bool
    version_leak: bool
    top_dense_score: float | None
    top_sparse_score: float | None


def section_matches(section_path: str, expected_sections: list[str]) -> bool:
    if not expected_sections:
        return True
    for section in expected_sections:
        if re.search(rf"(?:^|>\s*){re.escape(section)}(?=\s|$)", section_path):
            return True
    return False


def is_relevant(hit: FusedHit, case: dict[str, Any]) -> bool:
    payload = hit.payload
    if str(payload.get("document_id")) not in set(case["expected_document_ids"]):
        return False
    return section_matches(
        str(payload.get("section_path", "")),
        list(case.get("expected_sections", [])),
    )


def top_score(hits: list[FusedHit], attribute: str) -> float | None:
    values = [
        value
        for hit in hits
        if (value := getattr(hit, attribute)) is not None
    ]
    return max(values) if values else None


async def evaluate_case(
    retriever,
    settings: Settings,
    case: dict[str, Any],
    *,
    mode: str,
    k: int,
) -> CaseResult:
    as_of = case.get("as_of")
    filters = RetrievalFilters(
        as_of=date.fromisoformat(as_of) if as_of else None,
    )
    hits = await retriever.search(case["question"], filters=filters, limit=k, mode=mode)

    relevant_ranks = [
        rank for rank, hit in enumerate(hits, start=1) if is_relevant(hit, case)
    ]
    first_rank = relevant_ranks[0] if relevant_ranks else None
    relevant_count = len(relevant_ranks)
    decision = assess_evidence(
        hits,
        min_dense_score=settings.retrieval_min_dense_score,
        min_sparse_score=settings.retrieval_min_sparse_score,
        min_text_chars=settings.retrieval_min_text_chars,
    )
    leaked = any(
        str(hit.payload.get("status")) in LEAKED_STATUSES for hit in hits
    )

    return CaseResult(
        case_id=case["id"],
        mode=mode,
        category=case.get("category", "unknown"),
        top_documents=[str(hit.payload.get("document_id")) for hit in hits],
        relevant_rank=first_rank,
        recall=first_rank is not None,
        reciprocal_rank=1.0 / first_rank if first_rank else 0.0,
        context_precision=(relevant_count / len(hits)) if hits else 0.0,
        abstained=decision.inconclusive,
        abstention_reason=decision.reason,
        expected_abstention=bool(case.get("should_abstain", False)),
        version_leak=leaked,
        top_dense_score=top_score(hits, "dense_score"),
        top_sparse_score=top_score(hits, "sparse_score"),
    )


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    answerable = [result for result in results if not result.expected_abstention]
    abstention_cases = [result for result in results if result.expected_abstention]

    correct_abstentions = sum(result.abstained for result in abstention_cases)
    false_abstentions = sum(result.abstained for result in answerable)
    leak_cases = sum(result.version_leak for result in results)

    return {
        "cases": len(results),
        "answerable_cases": len(answerable),
        "abstention_cases": len(abstention_cases),
        "recall_at_k": (
            sum(result.recall for result in answerable) / len(answerable)
            if answerable
            else 0.0
        ),
        "mrr_at_k": (
            sum(result.reciprocal_rank for result in answerable) / len(answerable)
            if answerable
            else 0.0
        ),
        "context_precision_at_k": (
            sum(result.context_precision for result in answerable) / len(answerable)
            if answerable
            else 0.0
        ),
        "abstention_accuracy": (
            correct_abstentions / len(abstention_cases)
            if abstention_cases
            else 1.0
        ),
        "false_abstention_rate": (
            false_abstentions / len(answerable) if answerable else 0.0
        ),
        "version_leak_cases": leak_cases,
        "version_leak_rate": (leak_cases / len(results) if results else 0.0),
    }


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    retriever = build_retriever(settings)
    payload = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    cases = payload["cases"]

    if not cases:
        raise RuntimeError(f"no evaluation cases found in {QUESTIONS}")

    results: list[CaseResult] = []
    print(
        f"{'case':<9} {'mode':<8} {'expected':<24} {'top documents':<40} "
        f"{'rank':>4} {'abstain':>7}"
    )
    for case in cases:
        for mode in args.modes:
            result = await evaluate_case(
                retriever, settings, case, mode=mode, k=args.k
            )
            results.append(result)
            expected = ",".join(case["expected_document_ids"]) or "abstain"
            top_docs = ",".join(result.top_documents) or "-"
            print(
                f"{result.case_id:<9} {result.mode:<8} {expected:<24} "
                f"{top_docs[:40]:<40} {str(result.relevant_rank or '-'):>4} "
                f"{str(result.abstained):>7}"
            )

    summaries = {
        mode: summarize([result for result in results if result.mode == mode])
        for mode in args.modes
    }

    print("\nSummary")
    print(
        f"{'mode':<8} {'recall@k':>9} {'mrr@k':>8} {'precision@k':>12} "
        f"{'abstain acc':>12} {'false abstain':>14} {'leaks':>7}"
    )
    for mode, summary in summaries.items():
        print(
            f"{mode:<8} {summary['recall_at_k']:>9.3f} {summary['mrr_at_k']:>8.3f} "
            f"{summary['context_precision_at_k']:>12.3f} "
            f"{summary['abstention_accuracy']:>12.3f} "
            f"{summary['false_abstention_rate']:>14.3f} "
            f"{summary['version_leak_rate']:>7.3f}"
        )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = RESULTS_DIR / f"retrieval_results_{timestamp}.json"
    output.write_text(
        json.dumps(
            {
                "timestamp": timestamp,
                "k": args.k,
                "modes": args.modes,
                "thresholds": {
                    "min_dense_score": settings.retrieval_min_dense_score,
                    "min_sparse_score": settings.retrieval_min_sparse_score,
                    "min_text_chars": settings.retrieval_min_text_chars,
                },
                "summary": summaries,
                "cases": [asdict(result) for result in results],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote {output.relative_to(ROOT)}")

    failures: list[str] = []
    for mode, summary in summaries.items():
        if summary["version_leak_rate"] > 0:
            failures.append(f"{mode}: version leak rate {summary['version_leak_rate']:.3f}")
    hybrid_recall = summaries.get("hybrid", {}).get("recall_at_k", 0.0)
    if "hybrid" in summaries and hybrid_recall < args.min_recall:
        failures.append(
            f"hybrid: recall@{args.k} {hybrid_recall:.3f} below target {args.min_recall:.3f}"
        )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate policy retrieval quality.")
    parser.add_argument("--k", type=int, default=5, help="top-k cutoff (default 5)")
    parser.add_argument(
        "--modes",
        default="dense,sparse,hybrid",
        help="comma-separated retrieval modes",
    )
    parser.add_argument(
        "--min-recall",
        type=float,
        default=0.8,
        help="minimum hybrid recall@k required for a passing exit",
    )
    args = parser.parse_args()
    args.modes = tuple(mode.strip() for mode in args.modes.split(",") if mode.strip())
    unknown = sorted(set(args.modes) - set(MODES))
    if unknown:
        parser.error(f"unknown modes: {', '.join(unknown)}")
    if args.k <= 0:
        parser.error("--k must be positive")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
