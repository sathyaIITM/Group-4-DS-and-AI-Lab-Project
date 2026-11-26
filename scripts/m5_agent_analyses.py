"""Three agent analyses of the Milestone 5 report, recomputed from the committed test predictions.

    python scripts/m5_agent_analyses.py

1. Clarification (Section 6.1): on items whose validated gold expects a clarification, the share of
   runs in which the agent asked (outcome `clarifying`), and the share in which it also passed the
   scorer v3 `clarify_slot` check. Milestone 4 v2: its three runs re-scored on the validated gold;
   Milestone 5 versions: run 1.
2. Domain decision inside the agent (Section 6.2): the domain decision recorded for each test
   question in run 1, against the item's validated `domain` field: accuracy, expected calibration
   error (10 bins), mean confidence of correct and wrong decisions, and escalations to Jev.
3. v3 against v4 (Section 7): over the two runs of each version, the items that succeed less or more
   often in v4, and for each such item whether Kev (v4) and Jev (v3) made the same domain decision.

No model call. Writes `outputs/reports/m5_agent_analyses.json`.
"""

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyst.evaluation import e2e_eval, scorer_v3  # noqa: E402
from analyst.evaluation.e2e_eval import apply_gold, v3_checks  # noqa: E402

e2e_eval.SCORER_RULES = "v3"  # the values check of scorer v3, as `e2e_eval score --scorer v3`

PRED = ROOT / "outputs" / "predictions"
EVAL = ROOT / "data" / "eval"
OLD, NEW, T1 = (
    EVAL / f for f in ("e2e_test.v1.jsonl", "e2e_test_ext.v1.jsonl", "e2e_test_t1.v1.jsonl")
)
OUT = ROOT / "outputs" / "reports" / "m5_agent_analyses.json"


def _read(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _cases(pred_files: list[Path], gold_files: tuple[Path, ...]) -> list[list[dict[str, Any]]]:
    """One list of scored cases per run, restricted to the items of `gold_files`."""
    items = [i for f in gold_files for i in _read(f)]
    ids = {i["id"] for i in items}
    return [apply_gold([p for p in _read(f) if p["id"] in ids], items) for f in pred_files]


def _run_files(version: str, run: int, parts: tuple[str, ...]) -> list[Path]:
    name = {"main": f"m5_test_{version}_r{run}.jsonl", "t1": f"m5_test_t1_{version}_r{run}.jsonl"}
    return [PRED / name[p] for p in parts]


def clarification() -> dict[str, Any]:
    """Asked when it should, and with the right slot, on clarify items."""

    def rates(runs: list[list[dict[str, Any]]], with_slot: bool) -> dict[str, Any]:
        cases = [c for run in runs for c in run if c.get("expected_action") == "clarify"]
        asked = [c for c in cases if c["outcome"] == "clarifying"]
        out: dict[str, Any] = {"cases": len(cases), "asked": round(len(asked) / len(cases), 3)}
        if with_slot:
            slot = [c for c in asked if v3_checks(c).get("clarify_slot") is not False]
            out["asked_right_slot"] = round(len(slot) / len(cases), 3)
        return out

    m4 = sorted(PRED.glob("final_test_v2_r*.jsonl"))
    result: dict[str, Any] = {"m4_v2_continuity_3_runs": rates(_cases(m4, (OLD,)), False)}
    for v in ("v2", "v3", "v4"):
        main, t1 = _run_files(v, 1, ("main",)), _run_files(v, 1, ("t1",))
        result[f"m5_{v}_run1"] = {
            "continuity": rates(_cases(main, (OLD,)), True),
            "test_100": rates(_cases(main, (OLD, NEW)), True),
            "blind": rates(_cases(t1, (T1,)), True),
        }
    return result


def _domain_rows(files: list[Path], decision: str = "domain") -> list[dict[str, Any]]:
    gold = {i["id"]: i for f in (OLD, NEW, T1) for i in _read(f)}
    rows = []
    for f in files:
        for p in _read(f):
            records = [d for d in p.get("decisions") or [] if d.get("decision") == decision]
            if not records or not gold[p["id"]].get("domain"):
                continue
            d = records[-1]  # the decision for the asked question (the last turn)
            probs = d.get("probabilities") or {}
            rows.append(
                {
                    "id": p["id"],
                    "correct": d.get("label") == gold[p["id"]]["domain"],
                    "confidence": max(probs.values()) if probs else None,
                    "backend": d.get("backend"),
                    "escalated": bool(d.get("escalated")),
                }
            )
    return rows


def _ece(rows: list[dict[str, Any]], bins: int = 10) -> float:
    rs = [r for r in rows if r["confidence"] is not None]
    total = 0.0
    for b in range(bins):
        low, high = b / bins, (b + 1) / bins
        inside = [r for r in rs if low < r["confidence"] <= high]
        if inside:
            acc = sum(r["correct"] for r in inside) / len(inside)
            conf = sum(r["confidence"] for r in inside) / len(inside)
            total += len(inside) / len(rs) * abs(acc - conf)
    return round(total, 3)


def domain_inside_agent() -> dict[str, Any]:
    """Domain decisions of run 1 against the validated domain field."""
    result: dict[str, Any] = {}
    for name, version in (("v4_kev_ep3_s2", "v4"), ("v4_kev_joint", "v4joint"), ("v2_jev", "v2")):
        rows = _domain_rows(_run_files(version, 1, ("main", "t1")))
        right = [r["confidence"] for r in rows if r["correct"]]
        wrong = [r["confidence"] for r in rows if not r["correct"]]
        result[name] = {
            "decisions": len(rows),
            "accuracy": round(sum(r["correct"] for r in rows) / len(rows), 3),
            "ece": _ece(rows),
            "mean_confidence_correct": round(sum(right) / len(right), 3),
            "mean_confidence_wrong": round(sum(wrong) / len(wrong), 3),
            "escalated_to_jev": sum(r["escalated"] for r in rows),
        }
    tool = _domain_rows(_run_files("v4joint", 1, ("main", "t1")), "tool")
    result["v4_kev_joint"]["tool_escalated_to_jev"] = sum(r["escalated"] for r in tool)
    return result


def v3_against_v4() -> dict[str, Any]:
    """Items that change between v3 and v4 over two runs, and their domain decisions."""
    gold = {i["id"]: i for f in (OLD, NEW, T1) for i in _read(f)}
    runs: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
    for v in ("v3", "v4"):
        for r in (1, 2):
            cases = _cases(_run_files(v, r, ("main", "t1")), (OLD, NEW, T1))
            runs[(v, r)] = {c["id"]: c for run in cases for c in run}

    def success(v: str, i: str) -> float:
        return sum(scorer_v3.success(v3_checks(runs[(v, r)][i])) for r in (1, 2)) / 2

    def domain(v: str, r: int, i: str) -> str | None:
        records = [
            d for d in runs[(v, r)][i].get("decisions") or [] if d.get("decision") == "domain"
        ]
        return records[-1].get("label") if records else None

    def accuracy(v: str) -> float:
        pairs = [(domain(v, r, i), gold[i].get("domain")) for i in gold for r in (1, 2)]
        pairs = [(d, g) for d, g in pairs if d and g]
        return round(sum(d == g for d, g in pairs) / len(pairs), 3)

    worse = [i for i in sorted(gold) if success("v4", i) < success("v3", i)]
    better = [i for i in sorted(gold) if success("v4", i) > success("v3", i)]
    differing = [i for i in worse if any(domain("v3", r, i) != domain("v4", r, i) for r in (1, 2))]
    return {
        "items": len(gold),
        "worse_in_v4": len(worse),
        "better_in_v4": len(better),
        "worse_with_same_domain_decision_in_both_runs": len(worse) - len(differing),
        "worse_with_different_domain_decision": {
            i: {
                "v3_jev": [domain("v3", r, i) for r in (1, 2)],
                "v4_kev": [domain("v4", r, i) for r in (1, 2)],
                "gold": gold[i].get("domain"),
            }
            for i in differing
        },
        "domain_accuracy_both_runs": {"v3_jev": accuracy("v3"), "v4_kev": accuracy("v4")},
    }


def action_confusion() -> dict[str, Any]:
    """Expected action (validated gold) against the agent's outcome, run 1 of each version."""
    result: dict[str, Any] = {}
    for v in ("v2", "v3", "v4"):
        table: dict[str, dict[str, int]] = {}
        for run in _cases(_run_files(v, 1, ("main", "t1")), (OLD, NEW, T1)):
            for c in run:
                row = table.setdefault(c["expected_action"], {})
                row[c["outcome"]] = row.get(c["outcome"], 0) + 1
        result[f"{v}_run1"] = table
    return result


ROBUSTNESS_ITEMS = {
    "typos": ("e2e-020", "e2e-205", "e2e-428"),
    "hindi_hinglish": ("e2e-098", "e2e-201", "e2e-216", "e2e-227", "e2e-230"),
    "suppressed_value": ("e2e-092",),
}


def robustness_items() -> dict[str, Any]:
    """v4, two runs: outcome and scorer v3 success of the robustness items; follow-up items."""
    gold = {i["id"]: i for f in (OLD, NEW, T1) for i in _read(f)}
    runs = []
    for r in (1, 2):
        cases = _cases(_run_files("v4", r, ("main", "t1")), (OLD, NEW, T1))
        runs.append({c["id"]: c for run in cases for c in run})
    result: dict[str, Any] = {
        group: {
            i: [[run[i]["outcome"], scorer_v3.success(v3_checks(run[i]))] for run in runs]
            for i in ids
        }
        for group, ids in ROBUSTNESS_ITEMS.items()
    }
    follow = [i for i in gold if gold[i].get("prior_turns")]

    def share(ids: list[str]) -> float:
        hits = sum(scorer_v3.success(v3_checks(run[i])) for run in runs for i in ids)
        return round(hits / (len(runs) * len(ids)), 3)

    result["follow_ups"] = {
        "items": len(follow),
        "success": share(follow),
        "all_items": share(list(gold)),
    }
    return result


def main() -> None:
    """Compute the three analyses and write the report."""
    result = {
        "clarification": clarification(),
        "domain_inside_agent": domain_inside_agent(),
        "v3_against_v4": v3_against_v4(),
        "action_confusion": action_confusion(),
        "robustness_items": robustness_items(),
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
