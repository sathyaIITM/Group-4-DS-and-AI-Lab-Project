"""Compare run windows, flag drift signals, and create human-review suggestions."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

MIN_WINDOW = 50
PSI_STABLE = 0.10
PSI_ALERT = 0.25
PROP_MIN_EFFECT = 0.05


def psi_categorical(reference: list[Any], current: list[Any]) -> float:
    """Population Stability Index with a 0.5-count continuity correction."""
    if not reference or not current:
        raise ValueError("PSI windows must not be empty")
    categories = sorted(set(reference) | set(current), key=str)
    ref_counts = Counter(reference)
    cur_counts = Counter(current)
    ref_total, cur_total = len(reference), len(current)
    ref_den = ref_total + 0.5 * len(categories)
    cur_den = cur_total + 0.5 * len(categories)
    return float(
        sum(
            (cur - ref) * math.log(cur / ref)
            for category in categories
            for ref, cur in [
                (
                    (ref_counts[category] + 0.5) / ref_den,
                    (cur_counts[category] + 0.5) / cur_den,
                )
            ]
        )
    )


def ks_statistic(reference: list[float], current: list[float]) -> float:
    """Two-sample Kolmogorov-Smirnov distance, without a distributional p-value."""
    if not reference or not current:
        raise ValueError("KS windows must not be empty")
    ref, cur = (
        np.sort(np.asarray(reference, dtype=float)),
        np.sort(np.asarray(current, dtype=float)),
    )
    points = np.sort(np.concatenate((ref, cur)))
    ref_cdf = np.searchsorted(ref, points, side="right") / len(ref)
    cur_cdf = np.searchsorted(cur, points, side="right") / len(cur)
    return float(np.max(np.abs(ref_cdf - cur_cdf)))


def proportion_difference(reference: list[bool], current: list[bool]) -> dict[str, float | bool]:
    """Estimate a difference in proportions and a two-sided normal 95% interval."""
    if not reference or not current:
        raise ValueError("proportion windows must not be empty")
    p_ref = sum(reference) / len(reference)
    p_cur = sum(current) / len(current)
    difference = p_cur - p_ref
    standard_error = math.sqrt(
        p_ref * (1 - p_ref) / len(reference) + p_cur * (1 - p_cur) / len(current)
    )
    low, high = difference - 1.96 * standard_error, difference + 1.96 * standard_error
    return {
        "reference": p_ref,
        "current": p_cur,
        "difference": difference,
        "ci95_low": low,
        "ci95_high": high,
        "alert": (low > 0 or high < 0) and abs(difference) >= PROP_MIN_EFFECT,
    }


def _psi_verdict(value: float) -> str:
    if value < PSI_STABLE:
        return "stable"
    if value <= PSI_ALERT:
        return "watch"
    return "alert"


def _categorical_signal(
    name: str, reference: list[Any], current: list[Any], minimum: int
) -> dict[str, Any]:
    if min(len(reference), len(current)) < minimum:
        return {
            "name": name,
            "statistic": None,
            "verdict": "insufficient_data",
            "reference_n": len(reference),
            "current_n": len(current),
        }
    value = psi_categorical(reference, current)
    return {
        "name": name,
        "reference": dict(Counter(reference)),
        "current": dict(Counter(current)),
        "statistic": value,
        "statistic_name": "PSI",
        "verdict": _psi_verdict(value),
        "reference_n": len(reference),
        "current_n": len(current),
    }


def _continuous_signal(
    name: str, reference: Sequence[float], current: Sequence[float], minimum: int
) -> dict[str, Any]:
    if min(len(reference), len(current)) < minimum:
        return {
            "name": name,
            "statistic": None,
            "verdict": "insufficient_data",
            "reference_n": len(reference),
            "current_n": len(current),
        }
    value = ks_statistic(list(reference), list(current))
    return {
        "name": name,
        "reference": {"median": float(np.median(reference)), "mean": float(np.mean(reference))},
        "current": {"median": float(np.median(current)), "mean": float(np.mean(current))},
        "statistic": value,
        "statistic_name": "KS distance",
        "verdict": "watch" if value >= 0.10 else "stable",
        "reference_n": len(reference),
        "current_n": len(current),
    }


def _proportion_signal(
    name: str, reference: list[bool], current: list[bool], minimum: int
) -> dict[str, Any]:
    if min(len(reference), len(current)) < minimum:
        return {
            "name": name,
            "statistic": None,
            "verdict": "insufficient_data",
            "reference_n": len(reference),
            "current_n": len(current),
        }
    result = proportion_difference(reference, current)
    verdict = (
        "alert"
        if result["alert"]
        else ("watch" if abs(float(result["difference"])) >= PROP_MIN_EFFECT else "stable")
    )
    return {
        "name": name,
        **result,
        "statistic": result["difference"],
        "statistic_name": "difference of proportions",
        "verdict": verdict,
        "reference_n": len(reference),
        "current_n": len(current),
    }


def _relative_signal(
    name: str, reference: list[float], current: list[float], minimum: int
) -> dict[str, Any]:
    if min(len(reference), len(current)) < minimum:
        return {
            "name": name,
            "statistic": None,
            "verdict": "insufficient_data",
            "reference_n": len(reference),
            "current_n": len(current),
        }
    ref_value, cur_value = float(np.median(reference)), float(np.median(current))
    change = (
        (cur_value - ref_value) / abs(ref_value)
        if ref_value
        else (0.0 if cur_value == 0 else math.inf)
    )
    return {
        "name": name,
        "reference": ref_value,
        "current": cur_value,
        "statistic": change,
        "statistic_name": "relative change in median",
        "verdict": "watch" if abs(change) >= 0.20 else "stable",
        "reference_n": len(reference),
        "current_n": len(current),
    }


def _probabilities(row: dict[str, Any]) -> dict[str, float]:
    values = row.get("probabilities")
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except json.JSONDecodeError:
            values = {}
    return values if isinstance(values, dict) else {}


def _max_probability(row: dict[str, Any]) -> float | None:
    values = _probabilities(row)
    numbers = [float(value) for value in values.values() if isinstance(value, int | float)]
    return max(numbers) if numbers else None


def compare_windows(
    reference_runs: list[dict[str, Any]],
    current_runs: list[dict[str, Any]],
    *,
    reference_decisions: list[dict[str, Any]] | None = None,
    current_decisions: list[dict[str, Any]] | None = None,
    reference_checks: list[dict[str, Any]] | None = None,
    current_checks: list[dict[str, Any]] | None = None,
    data_events: list[dict[str, Any]] | None = None,
    catalogue_changed: bool = False,
    routing_floor: float | None = None,
    simulated: bool = False,
    minimum: int = MIN_WINDOW,
) -> dict[str, Any]:
    """Compare run-level, model-level and result-check signals for two evaluation windows."""
    ref_decisions = reference_decisions or []
    cur_decisions = current_decisions or []
    ref_checks = reference_checks or []
    cur_checks = current_checks or []
    signals: list[dict[str, Any]] = []
    for field, name in (("outcome", "outcome_shares"), ("cause", "failure_causes")):
        signals.append(
            _categorical_signal(
                name,
                [str(row.get(field) or "none") for row in reference_runs],
                [str(row.get(field) or "none") for row in current_runs],
                minimum,
            )
        )
    for outcome in sorted({str(row.get("outcome")) for row in reference_runs + current_runs}):
        signals.append(
            _proportion_signal(
                f"outcome:{outcome}",
                [row.get("outcome") == outcome for row in reference_runs],
                [row.get("outcome") == outcome for row in current_runs],
                minimum,
            )
        )
    for decision in ("tool", "domain"):
        ref_labels = [row.get("label") for row in ref_decisions if row.get("decision") == decision]
        cur_labels = [row.get("label") for row in cur_decisions if row.get("decision") == decision]
        signals.append(
            _categorical_signal(f"{decision}_label_shares", ref_labels, cur_labels, minimum)
        )
    ref_not_covered = [row.get("cause") in {"not_covered", "no_coverage"} for row in reference_runs]
    cur_not_covered = [row.get("cause") in {"not_covered", "no_coverage"} for row in current_runs]
    signals.append(
        _proportion_signal("not_covered_share", ref_not_covered, cur_not_covered, minimum)
    )
    for field, name in (
        ("unmatched_place", "unmatched_place_rate"),
        ("number_check_failed", "number_check_failure_rate"),
        ("sql_repairs", "sql_repair_rate"),
        ("widened_searches", "widened_search_rate"),
    ):
        signals.append(
            _proportion_signal(
                name,
                [bool(row.get(field)) for row in reference_runs],
                [bool(row.get(field)) for row in current_runs],
                minimum,
            )
        )
    ref_lengths = [len(str(row.get("question", ""))) for row in reference_runs]
    cur_lengths = [len(str(row.get("question", ""))) for row in current_runs]
    signals.append(_continuous_signal("question_length", ref_lengths, cur_lengths, minimum))

    ref_conf = [value for row in ref_decisions if (value := _max_probability(row)) is not None]
    cur_conf = [value for row in cur_decisions if (value := _max_probability(row)) is not None]
    signals.append(_continuous_signal("decision_confidence", ref_conf, cur_conf, minimum))
    signals.append(
        _categorical_signal(
            "decision_escalation",
            [bool(row.get("escalated")) for row in ref_decisions],
            [bool(row.get("escalated")) for row in cur_decisions],
            minimum,
        )
    )
    signals.append(
        _proportion_signal(
            "escalation_rate",
            [bool(row.get("escalated")) for row in ref_decisions],
            [bool(row.get("escalated")) for row in cur_decisions],
            minimum,
        )
    )
    ref_disagree = _disagreement_by_run(ref_decisions)
    cur_disagree = _disagreement_by_run(cur_decisions)
    signals.append(
        _proportion_signal(
            "escalated_decision_disagreement",
            [ref_disagree.get(str(row.get("run_id")), False) for row in reference_runs],
            [cur_disagree.get(str(row.get("run_id")), False) for row in current_runs],
            minimum,
        )
    )
    if routing_floor is not None:
        signals.append(
            _categorical_signal(
                "routing_below_floor",
                [(_max_probability(row) or 0.0) < routing_floor for row in ref_decisions],
                [(_max_probability(row) or 0.0) < routing_floor for row in cur_decisions],
                minimum,
            )
        )
    check_names = sorted({str(row.get("name")) for row in ref_checks + cur_checks})
    ref_run_ids = [str(row.get("run_id")) for row in reference_runs]
    cur_run_ids = [str(row.get("run_id")) for row in current_runs]
    for check_name in check_names:
        ref_failed = {
            str(row.get("run_id"))
            for row in ref_checks
            if str(row.get("name")) == check_name and not row.get("passed")
        }
        cur_failed = {
            str(row.get("run_id"))
            for row in cur_checks
            if str(row.get("name")) == check_name and not row.get("passed")
        }
        signals.append(
            _proportion_signal(
                f"result_check:{check_name}",
                [run_id in ref_failed for run_id in ref_run_ids],
                [run_id in cur_failed for run_id in cur_run_ids],
                minimum,
            )
        )

    for field in ("duration_ms", "cost_usd_est", "llm_calls"):
        ref_values = [float(row[field]) for row in reference_runs if row.get(field) is not None]
        cur_values = [float(row[field]) for row in current_runs if row.get(field) is not None]
        signals.append(_relative_signal(field, ref_values, cur_values, minimum))

    review_items: list[dict[str, str]] = []
    by_name = {signal["name"]: signal for signal in signals}
    if any(
        by_name.get(name, {}).get("verdict") in {"alert", "watch"}
        for name in ("decision_confidence", "decision_escalation")
    ):
        review_items.append(
            {
                "trigger": "decision_confidence_or_escalation_shift",
                "suggested_action": (
                    "Recalibrate the decision model on newly human-labelled examples."
                ),
            }
        )
    if any(
        by_name.get(name, {}).get("verdict") == "alert"
        for name in ("tool_label_shares", "domain_label_shares")
    ):
        review_items.append(
            {
                "trigger": "routing_label_shift",
                "suggested_action": (
                    "Label new cases and review the decision-model gate before retraining."
                ),
            }
        )
    if any(
        signal["name"].startswith("result_check:") and signal.get("verdict") in {"alert", "watch"}
        for signal in signals
    ):
        review_items.append(
            {
                "trigger": "result_check_failures",
                "suggested_action": (
                    "Inspect failing checks and the prompts that produced those answers."
                ),
            }
        )
    if by_name.get("not_covered_share", {}).get("verdict") in {"alert", "watch"}:
        review_items.append(
            {
                "trigger": "not_covered_shift",
                "suggested_action": "Review data requests and consider catalogue onboarding.",
            }
        )
    if data_events:
        review_items.extend(
            {
                "trigger": str(event.get("kind", "source_change")),
                "suggested_action": "Revalidate affected evaluation cases and verified examples.",
            }
            for event in data_events
        )
    if catalogue_changed:
        review_items.append(
            {
                "trigger": "catalogue_hash_changed",
                "suggested_action": (
                    "Revalidate the evaluation cases and rebuild retrieval knowledge."
                ),
            }
        )

    return {
        "created_at": datetime.now(UTC).isoformat(),
        "simulated": simulated,
        "reference_runs": len(reference_runs),
        "current_runs": len(current_runs),
        "minimum_window": minimum,
        "thresholds": {
            "psi_stable_below": PSI_STABLE,
            "psi_alert_above": PSI_ALERT,
            "proportion_min_effect": PROP_MIN_EFFECT,
        },
        "signals": signals,
        "review_items": review_items,
    }


def _disagreement_by_run(decisions: list[dict[str, Any]]) -> dict[str, bool]:
    labels: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    escalated: set[tuple[str, str]] = set()
    for row in decisions:
        run_id, decision = str(row.get("run_id")), str(row.get("decision"))
        if row.get("label") is not None:
            labels[run_id][decision].add(str(row["label"]))
        if row.get("escalated"):
            escalated.add((run_id, decision))
    return {
        run_id: any(
            (run_id, decision) in escalated and len(values) > 1
            for decision, values in by_decision.items()
        )
        for run_id, by_decision in labels.items()
    }


def load_window(
    db: Any, experiment: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Read a run window and related decisions and checks from the collated DuckDB warehouse."""
    columns = [row[0] for row in db.execute("DESCRIBE runs").fetchall()]
    runs = [
        dict(zip(columns, row, strict=True))
        for row in db.execute("SELECT * FROM runs WHERE experiment=?", [experiment]).fetchall()
    ]
    ids = [row["run_id"] for row in runs]
    if not ids:
        return runs, [], []
    placeholders = ",".join("?" for _ in ids)
    decisions = (
        db.execute(f"SELECT * FROM decisions WHERE run_id IN ({placeholders})", ids)  # noqa: S608 - placeholders and fixed table
        .fetchdf()
        .to_dict("records")
    )
    checks = (
        db.execute(f"SELECT * FROM checks WHERE run_id IN ({placeholders})", ids)  # noqa: S608 - placeholders and fixed table
        .fetchdf()
        .to_dict("records")
    )
    sql_attempts = db.execute(
        f"SELECT run_id, kind FROM sql_attempts WHERE run_id IN ({placeholders})",  # noqa: S608 - placeholders, table fixed
        ids,
    ).fetchall()
    sql_repairs = Counter(str(row[0]) for row in sql_attempts if row[1] == "repair")
    widened_rows = db.execute(
        f"SELECT run_id, widened FROM retrievals WHERE run_id IN ({placeholders})",  # noqa: S608 - placeholders, table fixed
        ids,
    ).fetchall()
    widened = Counter(str(row[0]) for row in widened_rows if row[1])
    artifacts = db.execute(
        f"SELECT run_id, plan, number_check FROM artifacts WHERE run_id IN ({placeholders})",  # noqa: S608 - placeholders, table fixed
        ids,
    ).fetchall()
    for run in runs:
        run_id = str(run["run_id"])
        run["sql_repairs"] = sql_repairs[run_id]
        run["widened_searches"] = widened[run_id]
        run["unmatched_place"] = False
        run["number_check_failed"] = False
    for run_id, plan_text, number_text in artifacts:
        matching = next((row for row in runs if str(row["run_id"]) == str(run_id)), None)
        if matching is None:
            continue
        try:
            plan = json.loads(plan_text) if plan_text else {}
            matching["unmatched_place"] = any(
                slot.get("slot") == "place" for slot in plan.get("unresolved", [])
            )
        except (TypeError, json.JSONDecodeError):
            pass
        try:
            number_check = json.loads(number_text) if number_text else None
            matching["number_check_failed"] = bool(
                number_check and not number_check.get("passed", False)
            )
        except (TypeError, json.JSONDecodeError):
            pass
    return runs, decisions, checks


def main() -> int:
    import duckdb

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warehouse", type=Path, default=Path("outputs/warehouse/runs.duckdb"))
    parser.add_argument("--reference-experiment", required=True)
    parser.add_argument("--current-experiment", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--simulated", action="store_true")
    parser.add_argument("--routing-floor", type=float)
    args = parser.parse_args()
    db = duckdb.connect(str(args.warehouse), read_only=True)
    ref_runs, ref_decisions, ref_checks = load_window(db, args.reference_experiment)
    cur_runs, cur_decisions, cur_checks = load_window(db, args.current_experiment)
    db.close()
    report = compare_windows(
        ref_runs,
        cur_runs,
        reference_decisions=ref_decisions,
        current_decisions=cur_decisions,
        reference_checks=ref_checks,
        current_checks=cur_checks,
        routing_floor=args.routing_floor,
        simulated=args.simulated,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
