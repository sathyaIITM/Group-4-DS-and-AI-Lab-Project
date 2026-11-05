"""Evaluate the domain decision (phase 1): run a served model, calibrate, score.

    # 1. serve a model (zero-shot or fine-tuned) with raw probabilities, e.g. in a Kev clone:
    #    KEV_TEMPERATURE=1.0 KEV_DTYPE=fp32 python -m kev.serve --run <checkpoint> --port 8009
    # 2. collect predictions for a split
    python -m analyst.evaluation.domain_eval run --split calibration --out <file>
    python -m analyst.evaluation.domain_eval run --split dev_synthetic --out <file>
    # 3. fit one temperature on calibration, score dev before and after
    python -m analyst.evaluation.domain_eval score --calibration <file> --dev <file>

The temperature is fitted on the calibration split only and applied unchanged to the dev split.
Labels are the rule-generated labels of the synthetic splits, so scores from this module are
engineering checks of the pipeline, not results on human labels.
"""

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import f1_score

from analyst.decisions.kev_questions import DOMAIN_OPTIONS
from analyst.decisions.phase1 import domain_question, read_jsonl, write_jsonl
from analyst.decisions.system_one import ChoiceQuestion, SystemOneClient
from analyst.evaluation.routing_eval import ece

ROOT = Path(__file__).resolve().parents[3]
SPLIT_DIR = ROOT / "data" / "splits" / "kev_domain"
LABELS = tuple(DOMAIN_OPTIONS)
N_BOOTSTRAP = 2000
SEED = 0


def run(
    client: SystemOneClient, records: list[dict[str, Any]], out: Path, limit: int | None = None
) -> None:
    """Ask the domain question for each record and write one prediction per line."""
    question = ChoiceQuestion.model_validate(domain_question())
    rows = []
    for record in records[:limit]:
        result = client.ask_choice(record["state"], {"domain": question})
        answer = result.answers["domain"]
        rows.append(
            {
                "id": record["_meta"]["id"],
                "label": record["questions"]["domain"]["label"],
                "predicted": answer.choice,
                "probabilities": answer.probabilities,
                "latency_s": result.latency_s,
            }
        )
    write_jsonl(out, rows)


def probability_matrix(rows: list[dict[str, Any]]) -> np.ndarray:
    """Rows of option probabilities in the fixed label order, renormalised to sum to 1."""
    matrix = np.array([[r["probabilities"][label] for label in LABELS] for r in rows], dtype=float)
    normalised: np.ndarray = matrix / matrix.sum(axis=1, keepdims=True)
    return normalised


def label_index(rows: list[dict[str, Any]]) -> np.ndarray:
    return np.array([LABELS.index(r["label"]) for r in rows])


def apply_temperature(probabilities: np.ndarray, temperature: float) -> np.ndarray:
    """Temperature scaling on log-probabilities; it never changes which option wins."""
    logits = np.log(np.clip(probabilities, 1e-12, 1.0)) / temperature
    logits -= logits.max(axis=1, keepdims=True)
    scaled = np.exp(logits)
    result: np.ndarray = scaled / scaled.sum(axis=1, keepdims=True)
    return result


def nll(probabilities: np.ndarray, truth: np.ndarray) -> float:
    return float(-np.log(np.clip(probabilities[np.arange(len(truth)), truth], 1e-12, 1.0)).mean())


def fit_temperature(probabilities: np.ndarray, truth: np.ndarray) -> float:
    """The temperature that minimises the negative log-likelihood, by a log-spaced search."""
    grid = np.exp(np.linspace(math.log(0.05), math.log(20.0), 600))
    losses = [nll(apply_temperature(probabilities, t), truth) for t in grid]
    return float(grid[int(np.argmin(losses))])


def brier(probabilities: np.ndarray, truth: np.ndarray) -> float:
    onehot = np.eye(probabilities.shape[1])[truth]
    return float(((probabilities - onehot) ** 2).sum(axis=1).mean())


def score(rows: list[dict[str, Any]], temperature: float = 1.0) -> dict[str, Any]:
    """Accuracy with a bootstrap interval, macro-F1, ECE, Brier, NLL and latency."""
    truth = label_index(rows)
    probabilities = apply_temperature(probability_matrix(rows), temperature)
    predicted = probabilities.argmax(axis=1)
    correct = (predicted == truth).astype(float)
    confidence = probabilities.max(axis=1)
    rng = np.random.default_rng(SEED)
    boot = [correct[rng.integers(0, len(correct), len(correct))].mean() for _ in range(N_BOOTSTRAP)]
    latency = np.array([r["latency_s"] for r in rows])
    index = list(range(len(LABELS)))
    return {
        "n": len(rows),
        "temperature": temperature,
        "accuracy": float(correct.mean()),
        "accuracy_ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
        "macro_f1": float(f1_score(truth, predicted, labels=index, average="macro")),
        "per_label_f1": dict(
            zip(
                LABELS,
                map(float, f1_score(truth, predicted, labels=index, average=None, zero_division=0)),
                strict=True,
            )
        ),
        "ece": ece(confidence, correct),
        "brier": brier(probabilities, truth),
        "nll": nll(probabilities, truth),
        "mean_confidence": float(confidence.mean()),
        "latency_s_median": float(np.median(latency)),
        "latency_s_p95": float(np.percentile(latency, 95)),
    }


def paired_bootstrap(
    rows_a: list[dict[str, Any]], rows_b: list[dict[str, Any]]
) -> dict[str, float | list[float]]:
    """Difference in accuracy (b minus a) on the same items, with a 95% bootstrap interval."""
    if [r["id"] for r in rows_a] != [r["id"] for r in rows_b]:
        msg = "the two prediction files must cover the same items in the same order"
        raise ValueError(msg)
    a = (label_index(rows_a) == probability_matrix(rows_a).argmax(axis=1)).astype(float)
    b = (label_index(rows_b) == probability_matrix(rows_b).argmax(axis=1)).astype(float)
    rng = np.random.default_rng(SEED)
    diffs = []
    for _ in range(N_BOOTSTRAP):
        pick = rng.integers(0, len(a), len(a))
        diffs.append(b[pick].mean() - a[pick].mean())
    return {
        "difference": float(b.mean() - a.mean()),
        "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
    }


def load_predictions(path: Path) -> list[dict[str, Any]]:
    return list(read_jsonl(path))


def report(calibration: Path, dev: Path) -> dict[str, Any]:
    """Fit the temperature on calibration; score dev with T=1 (raw) and with the fitted value."""
    cal_rows, dev_rows = load_predictions(calibration), load_predictions(dev)
    fitted = fit_temperature(probability_matrix(cal_rows), label_index(cal_rows))
    return {
        "calibration_n": len(cal_rows),
        "fitted_temperature": fitted,
        "dev_raw": score(dev_rows, 1.0),
        "dev_calibrated": score(dev_rows, fitted),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run_cmd = sub.add_parser("run")
    run_cmd.add_argument("--split", required=True)
    run_cmd.add_argument("--out", type=Path, required=True)
    run_cmd.add_argument("--limit", type=int)
    run_cmd.add_argument(
        "--base-url", default=os.environ.get("KEV_BASE_URL", "http://localhost:8009")
    )
    run_cmd.add_argument("--model", default="kev-latest")
    score_cmd = sub.add_parser("score")
    score_cmd.add_argument("--calibration", type=Path, required=True)
    score_cmd.add_argument("--dev", type=Path, required=True)
    score_cmd.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        client = SystemOneClient(args.base_url, args.model, os.environ.get("KEV_API_KEY"))
        try:
            records = list(read_jsonl(SPLIT_DIR / f"{args.split}.v1.jsonl"))
            run(client, records, args.out, args.limit)
        finally:
            client.close()
    else:
        result = report(args.calibration, args.dev)
        text = json.dumps(result, indent=2)
        if args.out:
            args.out.write_text(text + "\n", encoding="utf-8")
        print(text)


if __name__ == "__main__":
    main()
