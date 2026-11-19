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
    }


def _first_event_ms(state: Any) -> int | None:
    if not state.events:
        return None
    started = state.started_at
    first = min(event.at for event in state.events)
    return max(0, int((first - started).total_seconds() * 1000))


def _actual_dataset_ids(state: Any) -> list[str]:
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
            from analyst.agents.t3_nodes import live_t3_nodes

            nodes = live_t3_nodes(version, variant)
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
                    **({"slot_check": "manual"} if manual_slot else {}),
                }
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
    }


def score_repeats(paths: list[Path]) -> dict[str, Any]:
    """Score repeated run files and measure run-to-run changes in per-question correctness."""
    if not paths:
        raise ValueError("at least one predictions file is required")
    runs = [
        [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for path in paths
    ]
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


def _case_success(case: dict[str, Any]) -> bool:
    """Apply the primary answer/clarify/decline/describe/search scoring rules to one case."""
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
        correct_outcome = outcome == ("described" if expected == "describe" else "searched")
        return correct_outcome and required.issubset(retrieved)
    # A message outside the assistant's scope ends as out_of_scope (no data request is logged);
    # for scoring it is a correct decline.
    return expected == "decline" and outcome in {"declined", "out_of_scope"}


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
        entity in case.get("actual_entities", []) for entity in case.get("expected_entities", [])
    )
    return {
        "values_match": values_match,
        "narration_match": narration_match,
        "entity_match": entity_match,
    }


def _safe_precision(non_answer: list[bool], gold: list[bool]) -> float | None:
    from analyst.evaluation.metrics import abstention_precision

    value = abstention_precision(non_answer, gold)
    return value if math.isfinite(value) else None


def _safe_recall(non_answer: list[bool], gold: list[bool]) -> float | None:
    from analyst.evaluation.metrics import abstention_recall

    value = abstention_recall(non_answer, gold)
    return value if math.isfinite(value) else None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, default=str, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def _write_json(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(row, indent=2, default=str, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> int:
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
    report = score_repeats(args.predictions)
    report["experiment"] = report["runs"][0].get("experiment") if report["runs"] else None
    report["scored_at"] = datetime.now(UTC).isoformat()
    _write_json(args.out, report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
