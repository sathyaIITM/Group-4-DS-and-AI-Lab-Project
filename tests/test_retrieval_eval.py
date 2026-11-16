"""Tests for the retrieval evaluation (E7)."""

from pathlib import Path

from analyst.evaluation.retrieval_eval import RetrievalCase, case_scores, evaluate, load_cases

GOLD = Path("data/sample/rag_poc_retrieval_gold.v0.jsonl")


def test_case_scores() -> None:
    assert case_scores(["a"], ["b", "a", "c"], k=4) == {
        "recall": 1.0,
        "reciprocal_rank": 0.5,
        "ranks": {"a": 2},
    }
    assert case_scores(["a", "z"], ["a"], k=4)["recall"] == 0.5
    assert case_scores(["a"], ["b", "c", "d", "e", "a"], k=4)["recall"] == 0.0
    assert case_scores(["a"], ["b"], k=4)["reciprocal_rank"] == 0.0


def test_evaluate_skips_cases_without_a_table() -> None:
    cases = [
        RetrievalCase(id="1", question="q1", expected_dataset_ids=["a"]),
        RetrievalCase(id="2", question="q2", expected_dataset_ids=["b"]),
        RetrievalCase(id="3", question="q3", expected_dataset_ids=[]),
    ]
    ranking = {"q1": ["a", "b"], "q2": ["a", "c", "b"], "q3": ["a"]}
    result = evaluate(cases, lambda q: ranking[q], k=2)
    assert result["scored"] == 2
    assert result["recall_at_k"] == 0.5
    assert result["mrr"] == (1 + 1 / 3) / 2
    assert result["per_case"][2]["scored"] is False


def test_gold_file_matches_the_question_set() -> None:
    cases = load_cases(GOLD)
    assert [c.id for c in cases] == [f"rp-{i:02d}" for i in range(1, 13)]
    assert sum(1 for c in cases if not c.expected_dataset_ids) == 1
