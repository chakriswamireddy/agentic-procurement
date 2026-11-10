"""RAGAS-compatible RAG evaluation harness for policy retrieval and answers (Phase 6, Step 6.7)."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from app.rag.retriever import RetrievalFilters  # noqa: E402
from app.rag.runtime import build_retriever  # noqa: E402

DEFAULT_DATASET = ROOT / "data" / "evaluation" / "rag_questions.json"
RESULTS_DIR = ROOT / "data" / "evaluation" / "results"


def compute_lexical_overlap(text_a: str, text_b: str) -> float:
    """Compute token-level Jaccard similarity between two texts."""
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def evaluate_rag_case(case: dict[str, Any], retrieved_hits: list[Any]) -> dict[str, Any]:
    """Evaluate context recall, precision, and faithfulness for one RAG question."""
    expected_doc_ids = set(case.get("expected_document_ids", []))
    expected_keywords = [kw.lower() for kw in case.get("expected_keywords", [])]
    should_abstain = case.get("should_abstain", False)

    retrieved_doc_ids = [str(hit.payload.get("document_id")) for hit in retrieved_hits]
    retrieved_texts = [str(hit.payload.get("text", "")).lower() for hit in retrieved_hits]
    combined_context = " ".join(retrieved_texts)

    # 1. Context Recall: proportion of expected documents found in top hits
    if not expected_doc_ids:
        context_recall = 1.0 if not retrieved_hits else 0.5
    else:
        found_docs = set(retrieved_doc_ids) & expected_doc_ids
        context_recall = len(found_docs) / len(expected_doc_ids)

    # 2. Context Precision: are relevant documents ranked higher?
    if not retrieved_hits:
        context_precision = 1.0 if should_abstain else 0.0
    else:
        hits_relevant = [1 if doc_id in expected_doc_ids else 0 for doc_id in retrieved_doc_ids]
        cumulative = 0
        precisions = []
        for i, is_rel in enumerate(hits_relevant, start=1):
            if is_rel:
                cumulative += 1
                precisions.append(cumulative / i)
        context_precision = sum(precisions) / len(precisions) if precisions else 0.0

    # 3. Keyword / Fact Grounding (Faithfulness proxy)
    if not expected_keywords:
        faithfulness = 1.0
    else:
        found_keywords = sum(1 for kw in expected_keywords if kw in combined_context)
        faithfulness = found_keywords / len(expected_keywords)

    # 4. Answer Relevancy proxy (question token coverage in context)
    question = case.get("question", "")
    relevancy = compute_lexical_overlap(question, combined_context)

    return {
        "case_id": case.get("id"),
        "category": case.get("category"),
        "question": question,
        "retrieved_docs": retrieved_doc_ids[:5],
        "context_recall": round(context_recall, 4),
        "context_precision": round(context_precision, 4),
        "faithfulness": round(faithfulness, 4),
        "answer_relevancy": round(relevancy, 4),
        "abstained": len(retrieved_hits) == 0,
        "correct_abstention": (len(retrieved_hits) == 0) == should_abstain,
    }


async def run_rag_eval(
    dataset_path: Path = DEFAULT_DATASET,
    output_path: Path | None = None,
) -> dict[str, Any]:
    settings = Settings()
    retriever = build_retriever(settings)

    with open(dataset_path, encoding="utf-8") as f:
        data = json.load(f)

    dataset_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()[:12]
    cases = data.get("cases", [])

    results = []
    started = time.perf_counter()

    for case in cases:
        query = case.get("question", "")
        as_of = case.get("as_of")
        filters = RetrievalFilters(
            as_of=datetime.strptime(as_of, "%Y-%m-%d").date() if as_of else None,
        )
        hits = await retriever.search(query, filters=filters, limit=5, mode="hybrid")
        eval_result = evaluate_rag_case(case, hits)
        results.append(eval_result)

    total_time = round(time.perf_counter() - started, 2)

    avg_recall = sum(r["context_recall"] for r in results) / len(results) if results else 0.0
    avg_precision = sum(r["context_precision"] for r in results) / len(results) if results else 0.0
    avg_faithfulness = sum(r["faithfulness"] for r in results) / len(results) if results else 0.0
    avg_relevancy = sum(r["answer_relevancy"] for r in results) / len(results) if results else 0.0

    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "total_cases": len(results),
        "duration_seconds": total_time,
        "dataset_hash": dataset_hash,
        "metrics": {
            "mean_context_recall": round(avg_recall, 4),
            "mean_context_precision": round(avg_precision, 4),
            "mean_faithfulness": round(avg_faithfulness, 4),
            "mean_answer_relevancy": round(avg_relevancy, 4),
        },
        "cases": results,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate policy RAG retrieval and faithfulness")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    out_file = args.output
    if not out_file:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        out_file = RESULTS_DIR / f"rag_eval_{timestamp}.json"

    print(f"Running RAG evaluation on {args.dataset}...")
    summary = asyncio.run(run_rag_eval(args.dataset, out_file))

    metrics = summary["metrics"]
    print("\n--- RAG Evaluation Summary ---")
    print(f"Total cases evaluated:  {summary['total_cases']}")
    print(f"Mean Context Recall:     {metrics['mean_context_recall']:.4f}")
    print(f"Mean Context Precision:  {metrics['mean_context_precision']:.4f}")
    print(f"Mean Faithfulness:       {metrics['mean_faithfulness']:.4f}")
    print(f"Mean Answer Relevancy:   {metrics['mean_answer_relevancy']:.4f}")
    print(f"Saved detailed results:  {out_file}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
