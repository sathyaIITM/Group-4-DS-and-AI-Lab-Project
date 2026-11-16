"""Retrieval evaluation (E7): recall at k and mean reciprocal rank of the expected tables.

    python -m analyst.evaluation.retrieval_eval --cases <jsonl> [--k 4] [--out <json>]

A case is one JSON object per line with `id`, `question` and `expected_dataset_ids` (an empty
list when no catalogue table holds the answer; such cases are reported but not scored), and
optionally `expected_indicator_ids`. The retriever is the hybrid index of Milestone 3 (BM25 and
`bge-small-en-v1.5`, on pgvector when `POSTGRES_PASSWORD` is set, otherwise in memory).

Recall at k is the share of expected tables found in the top k, averaged over scored cases;
the reciprocal rank uses the first expected table found (0 when none is in the ranking).
"""

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_K = 4
DEPTH = 20


class RetrievalCase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    question: str
    expected_dataset_ids: list[str]
    expected_indicator_ids: list[str] = Field(default_factory=list)


def case_scores(expected: Sequence[str], ranked: Sequence[str], k: int) -> dict[str, Any]:
    ranks = {e: ranked.index(e) + 1 for e in expected if e in ranked}
    found = [e for e in expected if ranks.get(e, k + 1) <= k]
    first = min(ranks.values()) if ranks else None
    return {
        "recall": len(found) / len(expected),
        "reciprocal_rank": 1 / first if first else 0.0,
        "ranks": ranks,
    }


def evaluate(
    cases: Sequence[RetrievalCase],
    retrieve: Callable[[str], list[str]],
    k: int = DEFAULT_K,
    retrieve_indicators: Callable[[str], list[str]] | None = None,
) -> dict[str, Any]:
    """`retrieve(question)` returns dataset ids, best first (at least k deep)."""
    rows, recalls, rrs, ind_recalls = [], [], [], []
    for case in cases:
        ranked = retrieve(case.question)
        row: dict[str, Any] = {
            "id": case.id,
            "expected": case.expected_dataset_ids,
            "top": ranked[:k],
        }
        if case.expected_dataset_ids:
            scores = case_scores(case.expected_dataset_ids, ranked, k)
            row |= scores
            recalls.append(scores["recall"])
            rrs.append(scores["reciprocal_rank"])
        else:
            row["scored"] = False
        if retrieve_indicators and case.expected_indicator_ids:
            ind = case_scores(case.expected_indicator_ids, retrieve_indicators(case.question), k)
            row["indicator_recall"] = ind["recall"]
            ind_recalls.append(ind["recall"])
        rows.append(row)
    return {
        "k": k,
        "cases": len(cases),
        "scored": len(recalls),
        "recall_at_k": sum(recalls) / len(recalls) if recalls else None,
        "mrr": sum(rrs) / len(rrs) if rrs else None,
        "indicator_recall_at_k": sum(ind_recalls) / len(ind_recalls) if ind_recalls else None,
        "per_case": rows,
    }


def load_cases(path: Path) -> list[RetrievalCase]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [RetrievalCase.model_validate_json(x) for x in lines if x.strip()]


def hybrid_retrievers() -> tuple[Callable[[str], list[str]], Callable[[str], list[str]], str]:
    """Table and indicator retrievers over the Milestone 3 hybrid index."""
    from analyst.retrieval.hybrid import HybridIndex, database_url_from_env
    from analyst.retrieval.knowledge import build_entries

    index = HybridIndex(build_entries(), database_url_from_env())
    backend = index.build()

    def tables(question: str) -> list[str]:
        hits = index.search(question, "table", DEPTH)
        return [h.entry.dataset_id for h in hits if h.entry.dataset_id]

    def indicators(question: str) -> list[str]:
        hits = index.search(question, "indicator", DEPTH)
        return [str(h.entry.payload.get("indicator_id", h.entry.id)) for h in hits]

    return tables, indicators, backend


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    tables, indicators, backend = hybrid_retrievers()
    result = {"backend": backend, "cases_file": str(args.cases)}
    result |= evaluate(load_cases(args.cases), tables, args.k, indicators)
    text = json.dumps(result, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "per_case"}, indent=2))


if __name__ == "__main__":
    main()
