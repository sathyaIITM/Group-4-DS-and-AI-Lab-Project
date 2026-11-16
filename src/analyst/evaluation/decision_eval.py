"""Model evaluation for the Kev decisions (tool selection and domain), Milestone 4.

Extends `domain_eval` from one decision to any choice decision of `kev_questions.QUESTIONS`
and adds what the T3 brief (Section 7) asks for: AUROC of correctness, reliability diagrams,
cost per 1,000 decisions, the Kev-to-Jev cascade, the gate and the option-order flip rate.

    # collect predictions from a served backend (Kev locally, Jev, or Laya on the same route)
    python -m analyst.evaluation.decision_eval run --decision domain \
        --file data/splits/kev_domain/calibration.v1.jsonl --out <file> [--option-order-seed 1]
    # calibrate on one file, score another (before and after temperature)
    python -m analyst.evaluation.decision_eval score --decision domain \
        --calibration <cal> --dev <dev> [--figure outputs/figures/<name>.png]
    # gate: fine-tuned Kev against Jev on the same items
    python -m analyst.evaluation.decision_eval gate --decision domain \
        --kev-calibration <cal> --kev-dev <dev> --jev-dev <dev>
    # cascade: Kev answers above a threshold set on calibration, Jev answers the rest
    python -m analyst.evaluation.decision_eval cascade --decision domain \
        --kev-calibration <cal> --kev-dev <dev> --jev-dev <dev>
    # option-order flip rate over runs with different option orders
    python -m analyst.evaluation.decision_eval flips <order0> <order1> <order2>

A prediction file has one JSON object per line: `id`, `label`, `predicted`, `probabilities`
(every option), `latency_s` and optionally `cost_usd`. Scores on the synthetic splits are
engineering checks; the reported results use `dev_human`.
"""

import argparse
import json
import os
import random
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import f1_score, roc_auc_score

from analyst.decisions.kev_questions import QUESTIONS
from analyst.decisions.phase1 import read_jsonl, write_jsonl
from analyst.decisions.system_one import ChoiceQuestion, SystemOneClient
from analyst.evaluation.domain_eval import apply_temperature, brier, fit_temperature, nll
from analyst.evaluation.routing_eval import N_BINS, ece

N_BOOTSTRAP = 2000
SEED = 0
GATE_MARGIN = 0.03
GATE_ECE_MAX = 0.10
ERROR_BUDGET = 0.05

Rows = list[dict[str, Any]]


def labels_of(decision: str) -> tuple[str, ...]:
    return tuple(QUESTIONS[decision][1])


# ---------------------------------------------------------------------------- collection


def question_for(decision: str, order_seed: int | None = None) -> ChoiceQuestion:
    """The canonical question; with a seed, the same options in a shuffled order."""
    instructions, criteria = QUESTIONS[decision]
    items = list(criteria.items())
    if order_seed is not None:
        random.Random(order_seed).shuffle(items)  # noqa: S311 - reproducible order, not security
    return ChoiceQuestion(instructions=instructions, criteria=dict(items))


def run(
    client: SystemOneClient,
    records: Rows,
    decision: str,
    out: Path,
    order_seed: int | None = None,
    limit: int | None = None,
) -> int:
    """Ask one decision for each record; resumes when `out` already holds some ids."""
    done = {r["id"] for r in read_jsonl(out)} if out.exists() else set()
    rows = list(read_jsonl(out)) if out.exists() else []
    question = question_for(decision, order_seed)
    for record in records[:limit]:
        rid = record["_meta"]["id"]
        if rid in done:
            continue
        result = client.ask_choice(record["state"], {decision: question})
        answer = result.answers[decision]
        rows.append(
            {
                "id": rid,
                "label": record["questions"][decision]["label"],
                "predicted": answer.choice,
                "probabilities": answer.probabilities,
                "latency_s": result.latency_s,
                "input_tokens": result.input_tokens,
                "option_order_seed": order_seed,
            }
        )
        write_jsonl(out, rows)  # rewritten each time so an interrupted run can resume
    return len(rows)


# ---------------------------------------------------------------------------- arrays


def probability_matrix(rows: Rows, labels: tuple[str, ...]) -> np.ndarray:
    """Option probabilities in a fixed label order, renormalised to sum to 1."""
    matrix = np.array([[r["probabilities"].get(x, 0.0) for x in labels] for r in rows], float)
    sums = matrix.sum(axis=1, keepdims=True)
    if (sums <= 0).any():
        raise ValueError("a prediction has no probability mass on the label set")
    result: np.ndarray = matrix / sums
    return result


def truth_index(rows: Rows, labels: tuple[str, ...]) -> np.ndarray:
    unknown = {r["label"] for r in rows} - set(labels)
    if unknown:
        raise ValueError(f"labels outside the option set: {sorted(unknown)}")
    return np.array([labels.index(r["label"]) for r in rows])


def align(a: Rows, b: Rows) -> tuple[Rows, Rows]:
    """The items present in both files, in the order of `a`; labels must agree."""
    by_id = {r["id"]: r for r in b}
    shared = [r for r in a if r["id"] in by_id]
    if not shared:
        raise ValueError("the two prediction files share no item ids")
    other = [by_id[r["id"]] for r in shared]
    mismatched = [x["id"] for x, y in zip(shared, other, strict=True) if x["label"] != y["label"]]
    if mismatched:
        raise ValueError(f"labels differ between files for {mismatched[:5]}")
    return shared, other


# ---------------------------------------------------------------------------- metrics


def bootstrap_ci(values: np.ndarray, seed: int = SEED) -> list[float]:
    rng = np.random.default_rng(seed)
    n = len(values)
    means = [values[rng.integers(0, n, n)].mean() for _ in range(N_BOOTSTRAP)]
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def auroc_of_correctness(confidence: np.ndarray, correct: np.ndarray) -> float | None:
    """How well the confidence separates right from wrong answers; None if one class only."""
    if correct.min() == correct.max():
        return None
    return float(roc_auc_score(correct, confidence))


def reliability_bins(confidence: np.ndarray, correct: np.ndarray) -> list[dict[str, float]]:
    """Per equal-width bin: count, mean confidence and accuracy (the reliability diagram)."""
    edges = np.linspace(0.0, 1.0, N_BINS + 1)
    bins = np.clip(np.digitize(confidence, edges[1:-1]), 0, N_BINS - 1)
    out = []
    for b in range(N_BINS):
        mask = bins == b
        if mask.any():
            out.append(
                {
                    "low": float(edges[b]),
                    "high": float(edges[b + 1]),
                    "n": int(mask.sum()),
                    "confidence": float(confidence[mask].mean()),
                    "accuracy": float(correct[mask].mean()),
                }
            )
    return out


def score(rows: Rows, labels: tuple[str, ...], temperature: float = 1.0) -> dict[str, Any]:
    """Accuracy (bootstrap 95% CI), macro and per-label F1, NLL, Brier, ECE, AUROC, latency."""
    truth = truth_index(rows, labels)
    probabilities = apply_temperature(probability_matrix(rows, labels), temperature)
    predicted = probabilities.argmax(axis=1)
    correct = (predicted == truth).astype(float)
    confidence = probabilities.max(axis=1)
    index = list(range(len(labels)))
    per_label = f1_score(truth, predicted, labels=index, average=None, zero_division=0)
    latency = np.array([r.get("latency_s", 0.0) for r in rows], float)
    costs = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
    return {
        "n": len(rows),
        "temperature": temperature,
        "accuracy": float(correct.mean()),
        "accuracy_ci95": bootstrap_ci(correct),
        "macro_f1": float(
            f1_score(truth, predicted, labels=index, average="macro", zero_division=0)
        ),
        "per_label_f1": dict(zip(labels, map(float, per_label), strict=True)),
        "support": {x: int((truth == i).sum()) for i, x in enumerate(labels)},
        "nll": nll(probabilities, truth),
        "brier": brier(probabilities, truth),
        "ece": ece(confidence, correct),
        "auroc_correct": auroc_of_correctness(confidence, correct),
        "mean_confidence": float(confidence.mean()),
        "reliability": reliability_bins(confidence, correct),
        "latency_s_p50": float(np.median(latency)),
        "latency_s_p95": float(np.percentile(latency, 95)),
        "cost_usd_per_1000": float(np.mean(costs) * 1000) if costs else None,
    }


def calibrated_report(calibration: Rows, dev: Rows, labels: tuple[str, ...]) -> dict[str, Any]:
    """Fit one temperature on calibration; score dev raw and with that temperature."""
    fitted = fit_temperature(
        probability_matrix(calibration, labels), truth_index(calibration, labels)
    )
    return {
        "calibration_n": len(calibration),
        "fitted_temperature": fitted,
        "dev_raw": score(dev, labels, 1.0),
        "dev_calibrated": score(dev, labels, fitted),
    }


def _correct(rows: Rows, labels: tuple[str, ...], temperature: float = 1.0) -> np.ndarray:
    probabilities = apply_temperature(probability_matrix(rows, labels), temperature)
    result: np.ndarray = (probabilities.argmax(axis=1) == truth_index(rows, labels)).astype(float)
    return result


def paired_difference(a: np.ndarray, b: np.ndarray, seed: int = SEED) -> dict[str, Any]:
    """Accuracy of b minus a on the same items, with a paired bootstrap 95% interval."""
    rng = np.random.default_rng(seed)
    n = len(a)
    diffs = []
    for _ in range(N_BOOTSTRAP):
        pick = rng.integers(0, n, n)
        diffs.append(b[pick].mean() - a[pick].mean())
    return {
        "difference": float(b.mean() - a.mean()),
        "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
    }


def gate(
    kev_calibration: Rows,
    kev_dev: Rows,
    jev_dev: Rows,
    labels: tuple[str, ...],
    margin: float = GATE_MARGIN,
    ece_max: float = GATE_ECE_MAX,
) -> dict[str, Any]:
    """The adoption gate: Kev within `margin` of Jev on accuracy, and ECE <= `ece_max` after
    temperature scaling fitted on calibration. Both the point-estimate rule and the stricter
    non-inferiority rule (lower 95% bound above -margin) are reported; which one decides is
    fixed in configs/inference.yaml before the gate is run."""
    temperature = fit_temperature(
        probability_matrix(kev_calibration, labels), truth_index(kev_calibration, labels)
    )
    kev, jev = align(kev_dev, jev_dev)
    difference = paired_difference(_correct(jev, labels), _correct(kev, labels, temperature))
    kev_score = score(kev, labels, temperature)
    accuracy_ok = difference["difference"] >= -margin
    return {
        "n": len(kev),
        "kev_temperature": temperature,
        "kev_accuracy": kev_score["accuracy"],
        "jev_accuracy": float(_correct(jev, labels).mean()),
        "kev_minus_jev": difference,
        "kev_ece_calibrated": kev_score["ece"],
        "margin": margin,
        "ece_max": ece_max,
        "passes_point_estimate": bool(accuracy_ok and kev_score["ece"] <= ece_max),
        "passes_non_inferiority": bool(
            difference["ci95"][0] >= -margin and kev_score["ece"] <= ece_max
        ),
    }


def choose_threshold(
    confidence: np.ndarray, correct: np.ndarray, error_budget: float = ERROR_BUDGET
) -> float:
    """The lowest confidence threshold whose accepted items have an error rate within the
    budget (selective classification). Returns 1.01 (accept nothing) if none qualifies."""
    best = 1.01
    for t in sorted(set(confidence.tolist()), reverse=True):
        accepted = confidence >= t
        if 1.0 - correct[accepted].mean() <= error_budget:
            best = t
    return float(best)


def cascade(
    kev_calibration: Rows,
    kev_dev: Rows,
    jev_dev: Rows,
    labels: tuple[str, ...],
    error_budget: float = ERROR_BUDGET,
) -> dict[str, Any]:
    """Kev answers when its calibrated confidence reaches a threshold set on calibration;
    Jev answers the rest. Reports the share Kev handles and the cascade's accuracy and cost."""
    cal_probs = probability_matrix(kev_calibration, labels)
    cal_truth = truth_index(kev_calibration, labels)
    temperature = fit_temperature(cal_probs, cal_truth)
    scaled = apply_temperature(cal_probs, temperature)
    threshold = choose_threshold(
        scaled.max(axis=1), (scaled.argmax(axis=1) == cal_truth).astype(float), error_budget
    )
    kev, jev = align(kev_dev, jev_dev)
    probabilities = apply_temperature(probability_matrix(kev, labels), temperature)
    handled = probabilities.max(axis=1) >= threshold
    kev_correct, jev_correct = _correct(kev, labels, temperature), _correct(jev, labels)
    combined = np.where(handled, kev_correct, jev_correct)
    jev_costs = np.array([r.get("cost_usd") or 0.0 for r in jev], float)
    kev_costs = np.array([r.get("cost_usd") or 0.0 for r in kev], float)
    cost = np.where(handled, kev_costs, kev_costs + jev_costs)
    return {
        "n": len(kev),
        "error_budget": error_budget,
        "kev_temperature": temperature,
        "threshold": threshold,
        "escalation_band": [0.0, threshold],
        "kev_share": float(handled.mean()),
        "kev_error_on_handled": float(1 - kev_correct[handled].mean()) if handled.any() else None,
        "cascade_accuracy": float(combined.mean()),
        "cascade_accuracy_ci95": bootstrap_ci(combined),
        "kev_only_accuracy": float(kev_correct.mean()),
        "jev_only_accuracy": float(jev_correct.mean()),
        "cost_usd_per_1000": float(cost.mean() * 1000),
        "jev_calls_per_1000": float((~handled).mean() * 1000),
    }


def flip_rate(runs: list[Rows]) -> dict[str, Any]:
    """Share of items whose predicted label changes across option orders."""
    if len(runs) < 2:
        raise ValueError("need at least two runs with different option orders")
    ids = set.intersection(*({r["id"] for r in rows} for rows in runs))
    if not ids:
        raise ValueError("the runs share no item ids")
    by_run = [{r["id"]: r["predicted"] for r in rows} for rows in runs]
    flips = sum(len({run[i] for run in by_run}) > 1 for i in ids)
    return {"n": len(ids), "runs": len(runs), "flipped": flips, "flip_rate": flips / len(ids)}


# ---------------------------------------------------------------------------- figures


def plot_reliability(reports: dict[str, dict[str, Any]], path: Path, title: str) -> None:
    """One reliability diagram; each entry of `reports` is the output of `score`."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.plot([0, 1], [0, 1], linestyle="--", color="grey", linewidth=1, label="perfect")
    for name, result in reports.items():
        bins = result["reliability"]
        ax.plot(
            [b["confidence"] for b in bins],
            [b["accuracy"] for b in bins],
            marker="o",
            label=f"{name} (ECE {result['ece']:.3f})",
        )
    ax.set_xlabel("Mean confidence in bin")
    ax.set_ylabel("Accuracy in bin")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_title(title)
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------- CLI


def _load(path: Path) -> Rows:
    return list(read_jsonl(path))


def _emit(result: dict[str, Any], out: Path | None) -> None:
    text = json.dumps(result, indent=2)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run")
    run_cmd.add_argument("--decision", choices=list(QUESTIONS), required=True)
    run_cmd.add_argument("--file", type=Path, required=True)
    run_cmd.add_argument("--out", type=Path, required=True)
    run_cmd.add_argument("--option-order-seed", type=int)
    run_cmd.add_argument("--limit", type=int)
    run_cmd.add_argument(
        "--base-url", default=os.environ.get("KEV_BASE_URL", "http://localhost:8009")
    )
    run_cmd.add_argument("--model", default="kev-latest")
    run_cmd.add_argument("--api-key-env", default="KEV_API_KEY")

    score_cmd = sub.add_parser("score")
    score_cmd.add_argument("--decision", choices=list(QUESTIONS), required=True)
    score_cmd.add_argument("--calibration", type=Path, required=True)
    score_cmd.add_argument("--dev", type=Path, required=True)
    score_cmd.add_argument("--figure", type=Path)
    score_cmd.add_argument("--out", type=Path)

    for name in ("gate", "cascade"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--decision", choices=list(QUESTIONS), required=True)
        cmd.add_argument("--kev-calibration", type=Path, required=True)
        cmd.add_argument("--kev-dev", type=Path, required=True)
        cmd.add_argument("--jev-dev", type=Path, required=True)
        cmd.add_argument("--out", type=Path)

    flips_cmd = sub.add_parser("flips")
    flips_cmd.add_argument("runs", type=Path, nargs="+")
    flips_cmd.add_argument("--out", type=Path)

    args = parser.parse_args()
    if args.command == "run":
        client = SystemOneClient(args.base_url, args.model, os.environ.get(args.api_key_env))
        try:
            records = list(read_jsonl(args.file))
            n = run(client, records, args.decision, args.out, args.option_order_seed, args.limit)
        finally:
            client.close()
        print(f"wrote {n} predictions to {args.out}")
    elif args.command == "score":
        labels = labels_of(args.decision)
        result = calibrated_report(_load(args.calibration), _load(args.dev), labels)
        if args.figure:
            plot_reliability(
                {"raw": result["dev_raw"], "calibrated": result["dev_calibrated"]},
                args.figure,
                f"{args.decision}: {args.dev.stem}",
            )
        _emit(result, args.out)
    elif args.command in {"gate", "cascade"}:
        labels = labels_of(args.decision)
        fn = gate if args.command == "gate" else cascade
        _emit(
            fn(_load(args.kev_calibration), _load(args.kev_dev), _load(args.jev_dev), labels),
            args.out,
        )
    else:
        _emit(flip_rate([_load(p) for p in args.runs]), args.out)


if __name__ == "__main__":
    main()
