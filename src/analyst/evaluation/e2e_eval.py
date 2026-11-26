"""Split, run, verify and score the frozen end-to-end evaluation set."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from analyst.evaluation import scorer_v3
from analyst.evaluation.metrics import (
    accuracy_ci,
    execution_accuracy,
    latency_summary,
    success_rate,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SET = ROOT / "data" / "eval" / "e2e_v1.jsonl"
DEFAULT_PROCESSED = ROOT / "data" / "processed"
DEFAULT_WORKERS = 2


def load_set(path: Path) -> list[dict[str, Any]]:
    """Load JSONL evaluation cases and reject malformed or duplicate ids."""
    items = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("every evaluation row must be a JSON object")
    if not all(isinstance(item.get("id"), str) for item in items):
        raise ValueError("every evaluation row must have a string id")
    ids = [item.get("id") for item in items]
    if len(set(ids)) != len(ids):
        raise ValueError("evaluation set contains duplicate ids")
    if not all(isinstance(item, dict) and isinstance(item.get("question"), str) for item in items):
        raise ValueError("every evaluation row must be an object with a question")
    return items


def _bucket(item: dict[str, Any]) -> tuple[str, str]:
    """Return the stratification bucket of an item: expected action and first dataset."""
    action = str(item.get("expected_action", "unknown"))
    ids = item.get("dataset_ids") or []
    return action, str(ids[0]) if ids else "_none"


def split_items(
    items: list[dict[str, Any]], dev_size: int = 40, seed: int = 0
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Create a deterministic action/table-stratified split, retaining each follow-up case."""
    if not 0 < dev_size < len(items):
        raise ValueError("dev_size must be between zero and the number of items")
    rng = random.Random(seed)  # noqa: S311 - deterministic split, not a security token
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in items:
        buckets.setdefault(_bucket(item), []).append(item)
    total = len(items)
    allocations = {key: len(rows) * dev_size // total for key, rows in buckets.items()}
    remaining = dev_size - sum(allocations.values())
    remainders = sorted(
        buckets,
        key=lambda key: (-(len(buckets[key]) * dev_size % total), key),
    )
    for key in remainders[:remaining]:
        allocations[key] += 1
    dev: list[dict[str, Any]] = []
    test: list[dict[str, Any]] = []
    for key in sorted(buckets):
        rows = list(buckets[key])
        rng.shuffle(rows)
        dev.extend(rows[: allocations[key]])
        test.extend(rows[allocations[key] :])
    dev.sort(key=lambda item: item["id"])
    test.sort(key=lambda item: item["id"])
    if {item["id"] for item in dev} & {item["id"] for item in test}:
        raise AssertionError("split leaked ids")
    return dev, test


def write_split(
    source: Path = DEFAULT_SET,
    *,
    dev_path: Path | None = None,
    test_path: Path | None = None,
    dev_size: int = 40,
    seed: int = 0,
) -> dict[str, Any]:
    """Write the frozen development/test split and return checksums and dimensions."""
    dev_path = dev_path or source.with_name("e2e_dev.v1.jsonl")
    test_path = test_path or source.with_name("e2e_test.v1.jsonl")
    dev, test = split_items(load_set(source), dev_size=dev_size, seed=seed)
    _write_jsonl(dev_path, dev)
    _write_jsonl(test_path, test)

    def path_label(path: Path) -> str:
        """Return a path relative to the repository root when possible."""
        try:
            return path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            return str(path)

    return {
        "source": path_label(source),
        "source_sha256": _sha256(source),
        "dev": {"path": path_label(dev_path), "n": len(dev), "sha256": _sha256(dev_path)},
        "test": {"path": path_label(test_path), "n": len(test), "sha256": _sha256(test_path)},
        "seed": seed,
    }


def verify_gold(set_path: Path, processed: Path = DEFAULT_PROCESSED) -> dict[str, Any]:
    """Run shape checks and each answer's gold SQL through the read-only runner."""
    from scripts.check_e2e_set import check_action_rules, check_gold, check_shape

    from analyst.tools.sql_runner import ReadOnlyDatabase

    items = load_set(set_path)
    errors: list[str] = []
    tables = sorted({dataset for row in items for dataset in row.get("dataset_ids", [])})
    database = ReadOnlyDatabase(
        {f"obs_{table}": processed / f"obs_{table}.parquet" for table in tables}
    )
    for item in items:
        problems = check_shape(item)
        if not problems:
            problems.extend(check_action_rules(item))
            if item.get("expected_action") == "answer":
                problems.extend(check_gold(item, database))
        errors.extend(f"{item.get('id', '?')}: {problem}" for problem in problems)
    return {
        "set": str(set_path),
        "n": len(items),
        "validated_by_t1": all(row.get("validated") is True for row in items),
        "errors": errors,
    }


# Result columns that name what a value is about: places, and items such as a crop or commodity.
ENTITY_COLUMNS = {
    "entity",
    "geo_name",
    "geo_state",
    "geo_district",
    "place",
    "name",
    "commodity_name",
    "crop",
}


def _case_result(state: Any, item: dict[str, Any]) -> dict[str, Any]:
    """Build the prediction record of one evaluation case from the final agent state."""
    evidence = state.evidence
    result = state.result
    actual_numbers: list[float] = []
    if result is not None:
        for row in result.rows:
            for value in row:
                if isinstance(value, int | float) and not isinstance(value, bool):
                    actual_numbers.append(float(value))
    for derived in state.derived:
        if derived.output is not None:
            actual_numbers.append(float(derived.output))
    places: list[str] = []
    if result is not None:
        for index, column in enumerate(result.columns):
            if column.name.casefold() in ENTITY_COLUMNS:
                places.extend(str(row[index]) for row in result.rows if row[index] is not None)
    check = state.number_check
    return {
        "id": item["id"],
        "question": item["question"],
        "expected_action": item["expected_action"],
        "dataset_ids": item["dataset_ids"],
        "expected_values": item["expected_values"],
        "expected_entities": item["expected_entities"],
        "gold_sql": item.get("gold_sql"),
        "gold_rows": _gold_rows(item),
        "tolerance": item["tolerance"],
        "outcome": str(state.outcome.value if hasattr(state.outcome, "value") else state.outcome),
        "cause": state.outcome_cause,
        "response": state.response_text,
        "actual_numbers": actual_numbers,
        "narrated_numbers": _narrated_numbers(state.response_text),
        "actual_entities": places,
        "actual_dataset_ids": _actual_dataset_ids(state),
        "unresolved_slots": [slot.slot for slot in state.plan.unresolved] if state.plan else [],
        "notes": item.get("notes", ""),
        "clarification_text": state.response_text if state.outcome == "clarifying" else None,
        "number_check_passed": check.passed if check else None,
        "sql": result.sql if result else None,
        "result_columns": [column.name for column in result.columns] if result else [],
        "result_rows": result.rows if result else [],
        "checks": [outcome.model_dump(mode="json") for outcome in evidence.checks.outcomes]
        if evidence
        else [],
        "duration_ms": max(0, int((datetime.now(UTC) - state.started_at).total_seconds() * 1000)),
        "first_event_ms": _first_event_ms(state),
        "llm_calls": len(state.llm_records),
        "sql_repairs": sum(attempt.kind == "repair" for attempt in state.sql),
        "sql_attempts": len(state.sql),
        "narration_retries": max(0, len(state.narration) - 1),
        "widened_searches": state.counters.widened_searches,
        "tokens_in": sum(record.tokens_in for record in state.llm_records),
        "cached_tokens_in": sum(record.cached_tokens or 0 for record in state.llm_records),
        "tokens_out": sum(record.tokens_out for record in state.llm_records),
        "cost_usd_est": sum(record.cost_usd_est or 0.0 for record in state.llm_records),
        "run_id": state.run_id,
        # Every routing decision in order (route, then escalation): backend, label, calibrated
        # and raw probabilities, escalation, fallback, latency. Used to check Kev's confidence
        # inside the agent (v4) against the gold domain.
        "decisions": [_decision_record(record) for record in state.decision_log],
        **_interpretation_record(state),
        **gold_fields(item),
    }


GOLD_FIELDS = (
    "domain",
    "clarify_slot",
    "clarify_options",
    "expected_places",
    "expected_periods",
    "indicator_ids",
    "unit",
    "n_values",
    "gold_lineage",
    "gold_version",
)


def gold_fields(item: dict[str, Any]) -> dict[str, Any]:
    """The structured gold fields of an item (Milestone 5), copied into its case record."""
    return {name: item.get(name) for name in GOLD_FIELDS}


def _interpretation_record(state: Any) -> dict[str, Any]:
    """What scorer v3 reads from the final state: plan, clarification, evidence and chart."""
    plan = state.plan
    asked: list[str] = []
    options: list[str] = []
    if plan is not None:
        for slot in plan.unresolved:
            asked.append(slot.slot)
            options += slot.options
    intent = state.intent
    if intent is not None and intent.action == "clarify" and intent.missing_slot:
        asked.append(intent.missing_slot)
    if state.pending_clarification is not None and state.pending_clarification.options:
        options = list(state.pending_clarification.options)
    evidence = state.evidence
    return {
        "plan_places": [{"name": p.name, "level": p.level} for p in plan.places] if plan else [],
        "plan_all_places_level": plan.all_places_level if plan else None,
        "plan_periods": [
            {"start": w.start.isoformat(), "end": w.end.isoformat(), "label": w.label}
            for w in plan.periods
        ]
        if plan
        else [],
        "plan_indicators": [i.indicator_id for i in plan.indicators] if plan else [],
        "clarify_slots_asked": list(dict.fromkeys(asked)),
        "clarify_options_asked": options,
        "evidence": {
            "dataset_ids": sorted({s.dataset_id for s in evidence.sources}),
            "has_source": any(s.title and s.publisher for s in evidence.sources),
            "sql": evidence.sql,
        }
        if evidence is not None
        else {},
        "chart_attached": state.chart is not None,
    }


def _decision_record(record: Any) -> dict[str, Any]:
    """Dump a routing decision with the backend's raw probabilities restored.

    The router stores calibrated probabilities, p_cal proportional to p_raw ** (1 / T); the raw
    ones are p_raw proportional to p_cal ** T, exact up to the router's clipping at 1e-12.
    """
    row: dict[str, Any] = record.model_dump(mode="json")
    temperature = record.temperature
    if record.calibrated and temperature:
        powered = {
            k: max(float(v), 1e-12) ** float(temperature) for k, v in record.probabilities.items()
        }
        total = sum(powered.values())
        row["raw_probabilities"] = {k: v / total for k, v in powered.items()}
    else:
        row["raw_probabilities"] = dict(record.probabilities)
    return row


def _first_event_ms(state: Any) -> int | None:
    """Return milliseconds from the run start to its first event."""
    if not state.events:
        return None
    started = state.started_at
    first = min(event.at for event in state.events)
    return max(0, int((first - started).total_seconds() * 1000))


def _actual_dataset_ids(state: Any) -> list[str]:
    """Return every dataset the run considered or used."""
    ids: set[str] = set()
    if state.plan is not None:
        ids.add(state.plan.dataset_id)
    if state.intent is not None and state.intent.dataset_id != "none_fit":
        ids.add(state.intent.dataset_id)
    for candidate in state.catalogue_candidates:
        if candidate.get("dataset_id"):
            ids.add(str(candidate["dataset_id"]))
    for event in state.events:
        dataset_id = event.payload.get("dataset_id")
        if dataset_id:
            ids.add(str(dataset_id))
    return sorted(ids)


def _gold_rows(item: dict[str, Any]) -> list[list[Any]] | None:
    """Run an item's gold SQL and return its rows."""
    if not item.get("gold_sql"):
        return None
    from analyst.tools.sql_runner import ReadOnlyDatabase

    tables = item.get("dataset_ids", [])
    db = ReadOnlyDatabase(
        {f"obs_{table}": DEFAULT_PROCESSED / f"obs_{table}.parquet" for table in tables}
    )
    _, rows = db.run(item["gold_sql"])
    return [list(row) for row in rows]


def _narrated_numbers(text: str) -> list[float]:
    """Return the numbers stated in the narration, converted to base units."""
    from analyst.tools.units import convert_unit, parse_numbers

    values = []
    target_by_dimension = {
        "lakh": "persons",
        "crore": "persons",
        "thousand": "persons",
        "million": "persons",
        "lakh_inr": "inr",
        "crore_inr": "inr",
    }
    for parsed in parse_numbers(text):
        if parsed.is_period or parsed.is_reference:
            continue
        values.append(float(parsed.value))
        if parsed.unit_hint in target_by_dimension:
            # Also keep the base-unit value: the gold may be in persons or already in lakh.
            converted = convert_unit(
                parsed.value, parsed.unit_hint, target_by_dimension[parsed.unit_hint]
            )
            values.append(float(converted))
    return values


def _run_case(
    item: dict[str, Any],
    *,
    version: str,
    experiment: str,
    member: str,
    live: bool,
    variant: str | None = None,
) -> dict[str, Any]:
    """Run the agent on one evaluation item and return its prediction record."""
    from scripts.run_agent import run_one

    from analyst.agents.state import RunConfig

    conversation_id = str(uuid.uuid4())
    nodes = None
    meta = {
        "question_id": item["id"],
        "eval_set": str(item.get("eval_set", "e2e_dev")),
        "experiment": experiment,
        "member": member,
        "turn": "1",
    }
    start = time.perf_counter()
    prior_cost = 0.0
    prior_calls = prior_tokens_in = prior_tokens_out = 0
    try:
        if live:
            from analyst.agents.model_nodes import live_model_nodes

            nodes = live_model_nodes(version, variant)
        config = RunConfig.from_files(version, variant=variant)
        for turn_no, prior in enumerate(item.get("prior_turns", []), start=1):
            prior_state = run_one(
                prior,
                version=version,
                conversation_id=conversation_id,
                config=config,
                meta={**meta, "question_id": f"{item['id']}:prior-{turn_no}", "turn": str(turn_no)},
                nodes=nodes,
            )
            prior_cost += sum(record.cost_usd_est or 0.0 for record in prior_state.llm_records)
            prior_calls += len(prior_state.llm_records)
            prior_tokens_in += sum(record.tokens_in for record in prior_state.llm_records)
            prior_tokens_out += sum(record.tokens_out for record in prior_state.llm_records)
        state = run_one(
            item["question"],
            version=version,
            conversation_id=conversation_id,
            config=config,
            meta={**meta, "turn": str(len(item.get("prior_turns", [])) + 1)},
            nodes=nodes,
        )
    except Exception as error:
        return {
            "id": item["id"],
            "expected_action": item["expected_action"],
            "expected_values": item["expected_values"],
            "expected_entities": item["expected_entities"],
            "dataset_ids": item.get("dataset_ids", []),
            "actual_dataset_ids": [],
            "unresolved_slots": [],
            "notes": item.get("notes", ""),
            "tolerance": item["tolerance"],
            "experiment": experiment,
            "version": version,
            "member": member,
            **gold_fields(item),
            "outcome": "failed",
            "cause": "runner_exception",
            "error": f"{type(error).__name__}: {error}",
            "duration_ms": int((time.perf_counter() - start) * 1000),
            "cost_usd_est": 0.0,
            "llm_calls": 0,
            "tokens_in": 0,
            "tokens_out": 0,
        }
    result = _case_result(state, item)
    result["cost_usd_est"] += prior_cost
    result["llm_calls"] += prior_calls
    result["tokens_in"] += prior_tokens_in
    result["tokens_out"] += prior_tokens_out
    result.update(
        {"experiment": experiment, "version": version, "variant": variant, "member": member}
    )
    return result


def run_evaluation(
    set_path: Path | list[Path],
    out: Path,
    *,
    version: str,
    experiment: str,
    member: str,
    live: bool,
    workers: int = DEFAULT_WORKERS,
    allow_unvalidated: bool = False,
    eval_set: str | None = None,
    variant: str | None = None,
) -> list[dict[str, Any]]:
    """Run with at most two workers, preserving follow-ups and provider retries."""
    if workers < 1 or workers > DEFAULT_WORKERS:
        raise ValueError("workers must be 1 or 2; at most two questions may run in parallel")
    paths = set_path if isinstance(set_path, list) else [set_path]
    items = [item for path in paths for item in load_set(path)]
    if len({item["id"] for item in items}) != len(items):
        raise ValueError("the evaluation sets share item ids")
    test = any("test" in path.stem for path in paths)
    resolved_eval_set = eval_set or ("e2e_test" if test else "e2e_dev")
    items = [{**item, "eval_set": resolved_eval_set} for item in items]
    if not allow_unvalidated and any(not item.get("validated", False) for item in items):
        raise ValueError(
            "evaluation set includes unvalidated gold; T1 must validate it before runs"
        )
    gold_errors = [error for path in paths for error in verify_gold(path)["errors"]]
    if gold_errors:
        raise ValueError(
            f"gold verification failed ({len(gold_errors)} errors); see verify-gold report"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    try:  # build the retrieval index once, outside the timed runs
        from analyst.retrieval.catalogue import warm_up

        warm_up()
    except Exception as error:  # the agent falls back to lexical retrieval and logs it
        print(f"retrieval warm-up failed ({type(error).__name__}); lexical fallback in use")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(
                _run_case,
                item,
                version=version,
                experiment=experiment,
                member=member,
                live=live,
                variant=variant,
            )
            for item in items
        ]
        rows = [future.result() for future in futures]
    _write_jsonl(out, rows)
    return rows


def _within_tolerance(actual: float, expected: float, tolerance: float) -> bool:
    """Return True when a value matches the expected one within the tolerance."""
    return math.isclose(actual, expected, rel_tol=tolerance, abs_tol=1e-6)


def score_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Score primary success, execution, abstention, errors, latency, cost and retries per case."""
    successes: list[bool] = []
    wrong_answer: list[bool] = []
    non_answer: list[bool] = []
    gold_non_answer: list[bool] = []
    execution: list[bool | tuple[str, list[tuple[Any, ...]], list[tuple[Any, ...]]]] = []
    review: list[dict[str, Any]] = []
    outcomes: Counter[str] = Counter()
    for case in cases:
        expected = case.get("expected_action")
        outcome = case.get("outcome")
        outcomes[str(outcome)] += 1
        is_non_answer = outcome in {"declined", "out_of_scope", "abstained", "clarifying"}
        wants_non_answer = expected in {"decline", "clarify"}
        non_answer.append(is_non_answer)
        gold_non_answer.append(wants_non_answer)
        checks = _case_checks(case)
        correct = _case_success(case)
        if expected == "answer":
            if case.get("sql") and case.get("gold_rows") is not None and case.get("gold_sql"):
                execution.append((case["gold_sql"], case.get("result_rows", []), case["gold_rows"]))
            else:
                execution.append(False)
        successes.append(correct)
        wrong_answer.append(outcome in {"answered", "charted"} and not correct)
        manual_slot = (
            expected == "clarify" and outcome == "clarifying" and not case.get("unresolved_slots")
        )
        if not correct or manual_slot:
            review.append(
                {
                    "id": case.get("id"),
                    "expected": expected,
                    "outcome": outcome,
                    **checks,
                    **({"v3": v3_checks(case)} if SCORER_RULES == "v3" else {}),
                    **({"slot_check": "manual"} if manual_slot else {}),
                }
            )
    v3_rates = (
        scorer_v3.check_rates([v3_checks(case) for case in cases]) if SCORER_RULES == "v3" else None
    )
    latencies = [
        float(case["duration_ms"]) for case in cases if case.get("duration_ms") is not None
    ]
    first_events = [
        float(case["first_event_ms"]) for case in cases if case.get("first_event_ms") is not None
    ]
    answered = sum(case.get("outcome") in {"answered", "charted"} for case in cases)
    wrong_released = sum(wrong_answer)
    return {
        "n": len(cases),
        "success_rate": success_rate(successes) if successes else None,
        "success_ci95": list(accuracy_ci(successes)) if successes else None,
        "execution_accuracy": execution_accuracy(execution, projected=True) if execution else None,
        "abstention_precision": _safe_precision(non_answer, gold_non_answer),
        "abstention_recall": _safe_recall(non_answer, gold_non_answer),
        "wrong_answer_rate": wrong_released / answered if answered else None,
        "outcome_counts": dict(outcomes),
        "failure_rate": sum(case.get("outcome") == "failed" for case in cases) / len(cases)
        if cases
        else None,
        "failure_causes": dict(
            Counter(str(case.get("cause")) for case in cases if case.get("outcome") == "failed")
        ),
        "latency_ms": latency_summary(latencies) if latencies else None,
        "first_event_ms": latency_summary(first_events) if first_events else None,
        "calls_per_answered": sum(int(case.get("llm_calls", 0)) for case in cases) / answered
        if answered
        else None,
        "tokens_in": sum(int(case.get("tokens_in", 0)) for case in cases),
        "tokens_out": sum(int(case.get("tokens_out", 0)) for case in cases),
        "cost_usd_est": sum(float(case.get("cost_usd_est", 0.0) or 0.0) for case in cases),
        "cost_per_answered_usd_est": sum(
            float(case.get("cost_usd_est", 0.0) or 0.0) for case in cases
        )
        / answered
        if answered
        else None,
        "sql_repairs": sum(int(case.get("sql_repairs", 0)) for case in cases),
        "sql_attempts": sum(int(case.get("sql_attempts", 0)) for case in cases),
        "narration_retries": sum(int(case.get("narration_retries", 0)) for case in cases),
        "widened_searches": sum(int(case.get("widened_searches", 0)) for case in cases),
        "sql_repairs_per_run": sum(int(case.get("sql_repairs", 0)) for case in cases) / len(cases)
        if cases
        else None,
        "narration_retries_per_run": sum(int(case.get("narration_retries", 0)) for case in cases)
        / len(cases)
        if cases
        else None,
        "widened_searches_per_run": sum(int(case.get("widened_searches", 0)) for case in cases)
        / len(cases)
        if cases
        else None,
        "review_cases": review,
        **({"checks_v3": v3_rates} if v3_rates is not None else {}),
    }


def read_predictions(path: Path) -> list[dict[str, Any]]:
    """Read one predictions file (one case record per line)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def apply_gold(cases: list[dict[str, Any]], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace the gold copied into each case with the gold of the given set (same ids).

    Used to re-score earlier predictions on validated gold (Milestone 5). The agent's side of the
    record is untouched; the gold rows are recomputed from the gold SQL.
    """
    by_id = {str(item["id"]): item for item in items}
    missing = sorted({str(c["id"]) for c in cases} - set(by_id))
    if missing:
        raise ValueError(f"cases without an item in the gold set: {missing[:5]}")
    updated = []
    for case in cases:
        item = by_id[str(case["id"])]
        updated.append(
            {
                **case,
                "expected_action": item["expected_action"],
                "dataset_ids": item.get("dataset_ids", []),
                "expected_values": item["expected_values"],
                "expected_entities": item["expected_entities"],
                "tolerance": item["tolerance"],
                "notes": item.get("notes", ""),
                "gold_sql": item.get("gold_sql"),
                "gold_rows": _gold_rows(item),
                **gold_fields(item),
            }
        )
    return updated


def _load_runs(paths: list[Path], gold: list[dict[str, Any]] | None) -> list[list[dict[str, Any]]]:
    """Read repeated run files, with the gold replaced when a gold set is given."""
    runs = [read_predictions(path) for path in paths]
    return [apply_gold(cases, gold) for cases in runs] if gold is not None else runs


def compare_runs(
    a_paths: list[Path],
    b_paths: list[Path],
    gold: list[dict[str, Any]] | None = None,
    resamples: int = 10_000,
    seed: int = 0,
    only_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Paired comparison of two configurations on the same items (B minus A).

    `only_ids` restricts both sides to those items (for example the new test items, when one
    configuration was run on them only).

    Per item, the success rate over its repeated runs; the mean difference has a bootstrap 95%
    interval over items. An exact McNemar test compares majority success (at least half of the
    runs) per item.
    """
    import numpy as np
    from scipy.stats import binomtest

    def per_item(paths: list[Path]) -> dict[str, float]:
        runs = _load_runs(paths, gold)
        scores: dict[str, list[bool]] = {}
        for cases in runs:
            for case in cases:
                if only_ids is not None and str(case["id"]) not in only_ids:
                    continue
                scores.setdefault(str(case["id"]), []).append(_case_success(case))
        return {k: sum(v) / len(v) for k, v in scores.items()}

    a, b = per_item(a_paths), per_item(b_paths)
    if set(a) != set(b):
        raise ValueError("the two configurations were run on different items")
    ids = sorted(a)
    diff = np.array([b[i] - a[i] for i in ids])
    rng = np.random.default_rng(seed)
    means = diff[rng.integers(0, len(ids), size=(resamples, len(ids)))].mean(axis=1)
    a_major = [a[i] >= 0.5 for i in ids]
    b_major = [b[i] >= 0.5 for i in ids]
    only_b = sum(bb and not aa for aa, bb in zip(a_major, b_major, strict=True))
    only_a = sum(aa and not bb for aa, bb in zip(a_major, b_major, strict=True))
    discordant = only_a + only_b
    p_value = binomtest(only_b, discordant, 0.5).pvalue if discordant else 1.0
    return {
        "items": len(ids),
        "scorer_rules": SCORER_RULES,
        "a_success_mean": float(np.mean([a[i] for i in ids])),
        "b_success_mean": float(np.mean([b[i] for i in ids])),
        "difference_b_minus_a": float(diff.mean()),
        "difference_ci95": [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))],
        "bootstrap": {"resamples": resamples, "seed": seed},
        "mcnemar": {
            "only_a_succeeds": only_a,
            "only_b_succeeds": only_b,
            "p_value_exact": float(p_value),
        },
        "items_better_in_b": [i for i in ids if b[i] > a[i]],
        "items_worse_in_b": [i for i in ids if b[i] < a[i]],
    }


def score_repeats(paths: list[Path], gold: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Score repeated run files and measure run-to-run changes in per-question correctness."""
    if not paths:
        raise ValueError("at least one predictions file is required")
    runs = _load_runs(paths, gold)
    reports = [score_cases(cases) for cases in runs]
    indexed = [{str(case["id"]): _case_success(case) for case in cases} for cases in runs]
    common = set(indexed[0])
    for row in indexed[1:]:
        common &= set(row)
    if any(set(row) != set(indexed[0]) for row in indexed[1:]):
        raise ValueError("repeated run files must contain the same question ids")
    changed = sorted(item_id for item_id in common if len({row[item_id] for row in indexed}) > 1)
    rates = [float(report["success_rate"]) for report in reports]
    return {
        "repeats": len(paths),
        "runs": [
            {"path": str(path), **report} for path, report in zip(paths, reports, strict=True)
        ],
        "success_rate_mean": sum(rates) / len(rates),
        "success_rate_min": min(rates),
        "success_rate_max": max(rates),
        "success_rate_range": max(rates) - min(rates),
        "items_compared": len(common),
        "items_changed_correctness": changed,
        "run_to_run_instability": len(changed) / len(common) if common else None,
    }


def _v2_answer_ok(case: dict[str, Any]) -> bool:
    """Scorer v2 rule for an answer: values, narration, entities and the number check."""
    checks = _case_checks(case)
    return (
        case.get("outcome") in {"answered", "charted"}
        and checks["values_match"]
        and checks["narration_match"]
        and checks["entity_match"]
        and case.get("number_check_passed") is True
    )


def v3_checks(case: dict[str, Any]) -> dict[str, bool | None]:
    """Scorer v3 checks of one case (analyst.evaluation.scorer_v3)."""
    values_ok = _v2_answer_ok(case) if case.get("expected_action") == "answer" else False
    return scorer_v3.checks(case, values_ok, _within_tolerance, _tables_named)


def _case_success(case: dict[str, Any]) -> bool:
    """Apply the primary answer/clarify/decline/describe/search scoring rules to one case."""
    if SCORER_RULES == "v3":
        if not scorer_v3.computable(case):
            raise ValueError(
                f"{case.get('id')}: the record has no plan or evidence fields (written before "
                "Milestone 5); score it with --scorer v2"
            )
        return scorer_v3.success(v3_checks(case))
    expected, outcome = case.get("expected_action"), case.get("outcome")
    if expected == "answer":
        checks = _case_checks(case)
        return (
            outcome in {"answered", "charted"}
            and checks["values_match"]
            and checks["narration_match"]
            and checks["entity_match"]
            and case.get("number_check_passed") is True
        )
    if expected == "clarify":
        if outcome != "clarifying":
            return False
        # Resolution lists the missing slot; a clarification chosen by the router or by intent
        # extraction (before resolution) has no plan, and is checked by hand in the review list.
        unresolved = case.get("unresolved_slots", [])
        if not unresolved:
            return True
        required_slot = _expected_clarification_slot(str(case.get("notes", "")))
        return required_slot is not None and required_slot in unresolved
    if expected in {"describe", "search"}:
        required = set(case.get("dataset_ids", []))
        retrieved = set(case.get("actual_dataset_ids", []))
        if SCORER_RULES == "v2":
            retrieved |= _tables_named(case.get("response") or "")
        correct_outcome = outcome == ("described" if expected == "describe" else "searched")
        return correct_outcome and required.issubset(retrieved)
    # A message outside the assistant's scope ends as out_of_scope (no data request is logged);
    # for scoring it is a correct decline.
    return expected == "decline" and outcome in {"declined", "out_of_scope"}


# Scorer rules. v1: an expected entity must equal a value of an entity column, and a search or
# describe case must retrieve the gold tables. v2 (default, 19 Nov, after the M4 test ladder): an
# expected entity may also be a category value of a result row or a place plus a category value
# ("Bihar Rural" from geo_name "Bihar" and area "Rural"), and tables named in a search or describe
# reply count as retrieved. v1 is kept so the as-run M4 figures can be reproduced. v3 (Milestone
# 5): the checks of analyst.evaluation.scorer_v3 (interpretation, completeness, unit, period,
# evidence, clarification slot) on records written from Milestone 5 on.
SCORER_RULES = "v2"
NON_ENTITY_COLUMNS = {"period_label", "indicator_id", "unit", "quality_flag"}


def _entity_in_rows(entity: str, case: dict[str, Any]) -> bool:
    """Return True when a result row holds the entity, alone or as place plus category."""
    columns = [str(c).casefold() for c in case.get("result_columns", [])]
    wanted = " ".join(entity.casefold().split())
    for row in case.get("result_rows", []):
        cells = [
            " ".join(str(value).casefold().split())
            for column, value in zip(columns, row, strict=False)
            if isinstance(value, str) and column not in NON_ENTITY_COLUMNS
        ]
        if wanted in cells or any(f"{a} {b}" == wanted for a in cells for b in cells if a != b):
            return True
    return False


def _tables_named(text: str) -> set[str]:
    """Return the published dataset ids named in a text."""
    import re

    known = {p.stem.removeprefix("obs_") for p in DEFAULT_PROCESSED.glob("obs_*.parquet")}
    return {name for name in re.findall(r"\b[a-z0-9]+(?:_[a-z0-9]+)+\b", text) if name in known}


def _expected_clarification_slot(notes: str) -> str | None:
    """Map the human gold note's missing slot to the structured plan slot enum."""
    import re

    match = re.search(r"missing slot:\s*([^.;]+)", notes, flags=re.IGNORECASE)
    if match is None:
        return None
    raw = re.sub(r"\s+", " ", match.group(1).casefold()).strip()
    if "place" in raw or raw == "state" or "district" in raw:
        return "place" if raw != "state" else "geo_level"
    if "period" in raw or "year" in raw or "date" in raw:
        return "period"
    if raw in {"area", "population group", "commodity", "variety"}:
        return "category"
    return None


def _case_checks(case: dict[str, Any]) -> dict[str, bool]:
    """Return independent value, narration and entity match checks for review output."""
    tolerance = float(case.get("tolerance", 0.005))
    expected_values = case.get("expected_values", [])
    values_match = all(
        any(
            _within_tolerance(float(actual), float(expected), tolerance)
            for actual in case.get("actual_numbers", [])
        )
        for expected in expected_values
    )
    # A long series (more than 3 values) is shown by the chart and the rows; the narration
    # must state its first and last values only.
    narrated = (
        expected_values if len(expected_values) <= 3 else [expected_values[0], expected_values[-1]]
    )
    narration_match = all(
        any(
            _within_tolerance(float(actual), float(expected), tolerance)
            for actual in case.get("narrated_numbers", [])
        )
        for expected in narrated
    )
    entity_match = all(
        entity in case.get("actual_entities", [])
        or (SCORER_RULES == "v2" and _entity_in_rows(entity, case))
        for entity in case.get("expected_entities", [])
    )
    return {
        "values_match": values_match,
        "narration_match": narration_match,
        "entity_match": entity_match,
    }


def _safe_precision(non_answer: list[bool], gold: list[bool]) -> float | None:
    """Return abstention precision, or None when it is undefined."""
    from analyst.evaluation.metrics import abstention_precision

    value = abstention_precision(non_answer, gold)
    return value if math.isfinite(value) else None


def _safe_recall(non_answer: list[bool], gold: list[bool]) -> float | None:
    """Return abstention recall, or None when it is undefined."""
    from analyst.evaluation.metrics import abstention_recall

    value = abstention_recall(non_answer, gold)
    return value if math.isfinite(value) else None


def _sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write rows to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, default=str, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def _write_json(path: Path, row: dict[str, Any]) -> None:
    """Write one object to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(row, indent=2, default=str, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> int:
    """Command-line entry point for the end-to-end evaluation."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    split_parser = sub.add_parser("split")
    split_parser.add_argument("--set", type=Path, default=DEFAULT_SET)
    split_parser.add_argument("--dev-size", type=int, default=40)
    split_parser.add_argument("--seed", type=int, default=0)
    split_parser.add_argument(
        "--report", type=Path, default=ROOT / "outputs/reports/e2e_split.json"
    )
    verify_parser = sub.add_parser("verify-gold")
    verify_parser.add_argument("--set", type=Path, default=DEFAULT_SET)
    verify_parser.add_argument("--processed", type=Path, default=DEFAULT_PROCESSED)
    verify_parser.add_argument(
        "--out", type=Path, default=ROOT / "outputs/reports/e2e_gold_check.json"
    )
    run_parser = sub.add_parser("run")
    run_parser.add_argument(
        "--set", type=Path, nargs="+", required=True, help="one or more set files, run together"
    )
    run_parser.add_argument("--version", choices=[f"v{i}" for i in range(7)], required=True)
    run_parser.add_argument("--experiment", required=True)
    run_parser.add_argument(
        "--variant", default=None, help="an inference.yaml variant, such as jev_routing"
    )
    run_parser.add_argument("--member", choices=["T1", "T2", "T3", "T4"], default="T4")
    run_parser.add_argument("--out", type=Path, required=True)
    run_parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    run_parser.add_argument("--live", action="store_true")
    run_parser.add_argument(
        "--yes", action="store_true", help="confirm live calls may spend credit"
    )
    run_parser.add_argument("--allow-unvalidated", action="store_true")
    score_parser = sub.add_parser("score")
    score_parser.add_argument("--predictions", type=Path, nargs="+", required=True)
    score_parser.add_argument("--out", type=Path, required=True)
    score_parser.add_argument(
        "--scorer",
        choices=["v1", "v2", "v3"],
        default="v2",
        help="scorer rules (v1: as-run M4; v3: Milestone 5 records)",
    )
    score_parser.add_argument(
        "--gold", type=Path, nargs="+", help="score against the gold of these sets (same ids)"
    )
    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("--a", type=Path, nargs="+", required=True, help="baseline runs")
    compare_parser.add_argument("--b", type=Path, nargs="+", required=True, help="new runs")
    compare_parser.add_argument("--scorer", choices=["v1", "v2", "v3"], default="v3")
    compare_parser.add_argument("--gold", type=Path, nargs="+")
    compare_parser.add_argument("--only", type=Path, help="compare only the items of this set")
    compare_parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "split":
        report = write_split(args.set, dev_size=args.dev_size, seed=args.seed)
        _write_json(args.report, report)
        print(json.dumps(report, indent=2))
        return 0
    if args.command == "verify-gold":
        report = verify_gold(args.set, args.processed)
        _write_json(args.out, report)
        print(f"{len(report['errors'])} errors; report: {args.out}")
        return int(bool(report["errors"]))
    if args.command == "run":
        if args.live and not args.yes:
            parser.error("live evaluation calls may spend cloud credit; add --yes")
        if args.live and args.workers > DEFAULT_WORKERS:
            parser.error("live runs allow at most two questions in parallel")
        rows = run_evaluation(
            args.set,
            args.out,
            version=args.version,
            experiment=args.experiment,
            member=args.member,
            live=args.live,
            workers=args.workers,
            allow_unvalidated=args.allow_unvalidated,
            variant=args.variant,
        )
        print(f"{len(rows)} questions written to {args.out}")
        return 0
    global SCORER_RULES
    SCORER_RULES = args.scorer
    gold = [item for path in args.gold for item in load_set(path)] if args.gold else None
    if args.command == "compare":
        only = {str(i["id"]) for i in load_set(args.only)} if args.only else None
        comparison = compare_runs(args.a, args.b, gold, only_ids=only)
        comparison.update(
            a=[str(p) for p in args.a],
            b=[str(p) for p in args.b],
            gold=[str(p) for p in args.gold] if args.gold else None,
            compared_at=datetime.now(UTC).isoformat(),
        )
        _write_json(args.out, comparison)
        print(json.dumps(comparison, indent=2))
        return 0
    report = score_repeats(args.predictions, gold)
    report["scorer_rules"] = args.scorer
    report["gold"] = [str(p) for p in args.gold] if args.gold else None
    report["experiment"] = report["runs"][0].get("experiment") if report["runs"] else None
    report["scored_at"] = datetime.now(UTC).isoformat()
    _write_json(args.out, report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
