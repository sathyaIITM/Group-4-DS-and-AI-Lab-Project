"""v5 component check: can a zero-shot Jev verifier tell correct released answers from wrong ones?

    set -a; source .env; set +a
    python scripts/v5_verifier_check.py run      # asks Jev (two questions per answer; Jev credit)
    python scripts/v5_verifier_check.py score    # no model call

Takes every answer v4 released in its first test run
(`outputs/predictions/m5_test{,_t1}_v4_r1.jsonl`, 140 items) and asks Jev two yes-or-no questions
about it, with the question, the answer, the tables used, the SQL and the query result as the
state: are the answer's figures and claims supported by the result, and does the answer address
what the question asks. Nothing is tuned: Jev is zero-shot, the verifier score is the product of
the two probabilities and the decision threshold is 0.5. The reference label is whether the answer
passes every scorer v3 check against the validated gold. This is a component result for planning v5
(Milestone 6), not a calibrated verifier: the test items were seen before this check was written,
so it is reported as a first measurement, not as v5's result. Writes
`outputs/predictions/v5_verifier_v4_r1.jsonl` and `outputs/reports/v5_verifier_component.json`.
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyst.decisions.system_one import NoulQuestion, SystemOneClient  # noqa: E402
from analyst.evaluation import e2e_eval, scorer_v3  # noqa: E402
from analyst.evaluation.e2e_eval import apply_gold, v3_checks  # noqa: E402

e2e_eval.SCORER_RULES = "v3"  # the values check of scorer v3, as `e2e_eval score --scorer v3`

PRED = ROOT / "outputs" / "predictions"
RUNS = (PRED / "m5_test_v4_r1.jsonl", PRED / "m5_test_t1_v4_r1.jsonl")
GOLD = tuple(
    ROOT / "data" / "eval" / f
    for f in ("e2e_test.v1.jsonl", "e2e_test_ext.v1.jsonl", "e2e_test_t1.v1.jsonl")
)
OUT = PRED / "v5_verifier_v4_r1.jsonl"
REPORT = ROOT / "outputs" / "reports" / "v5_verifier_component.json"
THRESHOLD = 0.5
MAX_ROWS = 40
QUESTIONS = {
    "claims_supported": NoulQuestion(
        instructions=(
            "Is every figure, place, period and unit stated in the answer supported by the query "
            "result rows shown? Answer no if any stated number is absent from or contradicts the "
            "result, or if the answer describes a place, period or measure the result does not "
            "hold."
        )
    ),
    "intent_aligned": NoulQuestion(
        instructions=(
            "Does the answer address what the question asks: the same place, period and measure, "
            "and for a comparison, ranking or series every value the question asks for? Answer no "
            "if it answers a different question or leaves out part of what was asked."
        )
    ),
}


def _cases() -> list[dict]:
    items = [json.loads(x) for f in GOLD for x in f.read_text(encoding="utf-8").splitlines() if x]
    preds = [json.loads(x) for f in RUNS for x in f.read_text(encoding="utf-8").splitlines() if x]
    return [c for c in apply_gold(preds, items) if c["outcome"] == "answered"]


def _state(case: dict) -> str:
    rows = case.get("result_rows") or []
    lines = [
        f"Question: {case['question']}",
        f"Answer: {case.get('response') or ''}",
        f"Tables used: {', '.join(case.get('actual_dataset_ids') or [])}",
        f"SQL: {case.get('sql') or ''}",
        f"Query result ({len(rows)} rows; first {min(len(rows), MAX_ROWS)} shown):",
        *[json.dumps(r, ensure_ascii=False, default=str) for r in rows[:MAX_ROWS]],
    ]
    return "\n".join(lines)


def run() -> None:
    """Ask Jev about every released answer."""
    client = SystemOneClient(
        "https://api.typesafe.ai", "jev-latest", os.environ["TYPESAFE_API_KEY"]
    )
    out = []
    try:
        for case in _cases():
            answer = client.ask(_state(case), QUESTIONS)
            correct = scorer_v3.success(v3_checks(case))
            out.append(
                {
                    "id": case["id"],
                    "correct": bool(correct),
                    **answer.probabilities,
                    "latency_s": round(answer.latency_s, 3),
                }
            )
    finally:
        client.close()
    OUT.write_text("".join(json.dumps(r) + "\n" for r in out), encoding="utf-8")
    print(f"wrote {len(out)} verdicts to {OUT.relative_to(ROOT)}")


def score() -> None:
    """Separation of correct and wrong answers by the verifier score."""
    rows = [json.loads(x) for x in OUT.read_text(encoding="utf-8").splitlines() if x]
    # Labels are recomputed from the scorer here, so they always follow the current scorer v3.
    labels = {c["id"]: bool(scorer_v3.success(v3_checks(c))) for c in _cases()}
    correct = np.array([labels[r["id"]] for r in rows])
    p_ok = np.array([r["claims_supported"] * r["intent_aligned"] for r in rows])
    keep = p_ok >= THRESHOLD
    wrong = ~correct
    result = {
        "released_answers": len(rows),
        "correct": int(correct.sum()),
        "wrong": int(wrong.sum()),
        "auroc_correct_vs_wrong": round(float(roc_auc_score(correct, p_ok)), 3),
        "threshold": THRESHOLD,
        "wrong_flagged": int((wrong & ~keep).sum()),
        "correct_flagged": int((correct & ~keep).sum()),
        "precision_released_before": round(float(correct.mean()), 3),
        "precision_released_after": round(float(correct[keep].mean()), 3) if keep.any() else None,
        "answers_kept": int(keep.sum()),
        "mean_score_correct": round(float(p_ok[correct].mean()), 3),
        "mean_score_wrong": round(float(p_ok[wrong].mean()), 3) if wrong.any() else None,
        "latency_s_p50": round(float(np.median([r["latency_s"] for r in rows])), 3),
    }
    REPORT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    {"run": run, "score": score}[sys.argv[1] if len(sys.argv) > 1 else "score"]()
