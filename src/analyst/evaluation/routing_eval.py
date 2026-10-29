"""Score and run the tool-selection (routing) decision.

Usage (from the repository root):
    python -m analyst.evaluation.routing_eval run --backend kev \
        --out outputs/week1/routing_kev.jsonl
    python -m analyst.evaluation.routing_eval score outputs/week1/routing_kev.jsonl
"""

import argparse
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import f1_score

from analyst.decisions.routing import TOOLS, RoutingExample, RoutingPrediction, route
from analyst.decisions.system_one import SystemOneClient

EXAMPLES = Path("data/sample/routing_week1.jsonl")
BACKENDS = {
    "kev": ("http://127.0.0.1:8009", "kev-latest", "KEV_API_KEY"),
    "jev": ("https://api.typesafe.ai", "jev-latest", "TYPESAFE_API_KEY"),
}
N_BINS = 10
N_BOOTSTRAP = 2000
SEED = 0


def load_examples(path: Path = EXAMPLES, labels: Path | None = None) -> list[RoutingExample]:
    """Read examples; `labels` (JSONL of id, label) overrides the stored labels."""
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if labels is not None:
        override = {
            r["id"]: r["label"]
            for r in (json.loads(x) for x in labels.read_text().splitlines() if x.strip())
        }
        for row in rows:
            row["label"] = override.get(row["id"], row["label"])
    return [RoutingExample.model_validate(row) for row in rows]


def run(backend: str, examples: list[RoutingExample], out: Path) -> None:
    """Query one backend for every example, appending to `out`; resumes if it exists."""
    base_url, model, key_var = BACKENDS[backend]
    done = set()
    if out.exists():
        done = {json.loads(x)["id"] for x in out.read_text().splitlines() if x.strip()}
    out.parent.mkdir(parents=True, exist_ok=True)
    client = SystemOneClient(base_url, model, api_key=os.environ.get(key_var))
    try:
        with out.open("a") as handle:
            for example in examples:
                if example.id in done:
                    continue
                handle.write(route(client, example).model_dump_json() + "\n")
                handle.flush()
    finally:
        client.close()


def _confidence(prediction: RoutingPrediction) -> float:
    """Share of the summed yes-probabilities held by the chosen tool."""
    total = sum(prediction.probabilities.values())
    return prediction.probabilities[prediction.predicted] / total if total > 0 else 0.0


def ece(confidence: np.ndarray, correct: np.ndarray) -> float:
    """Expected calibration error with equal-width bins."""
    edges = np.linspace(0.0, 1.0, N_BINS + 1)
    bins = np.clip(np.digitize(confidence, edges[1:-1]), 0, N_BINS - 1)
    error = 0.0
    for b in range(N_BINS):
        mask = bins == b
        if mask.any():
            error += mask.mean() * abs(correct[mask].mean() - confidence[mask].mean())
    return float(error)


def score(predictions: list[RoutingPrediction]) -> dict[str, Any]:
    """Accuracy with a bootstrap interval, macro-F1, ECE, chance baselines and latency."""
    labels = np.array([p.label for p in predictions])
    predicted = np.array([p.predicted for p in predictions])
    correct = (labels == predicted).astype(float)
    confidence = np.array([_confidence(p) for p in predictions])
    rng = np.random.default_rng(SEED)
    boot = [correct[rng.integers(0, len(correct), len(correct))].mean() for _ in range(N_BOOTSTRAP)]
    counts = {tool: int((labels == tool).sum()) for tool in TOOLS}
    latency = np.array([p.latency_s for p in predictions])
    return {
        "n": len(predictions),
        "accuracy": float(correct.mean()),
        "accuracy_ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
        "macro_f1": float(f1_score(labels, predicted, labels=list(TOOLS), average="macro")),
        "per_tool_f1": dict(
            zip(
                TOOLS,
                map(float, f1_score(labels, predicted, labels=list(TOOLS), average=None)),
                strict=True,
            )
        ),
        "ece_uncalibrated": ece(confidence, correct),
        "chance_uniform": 1 / len(TOOLS),
        "chance_majority": max(counts.values()) / len(predictions),
        "label_counts": counts,
        "latency_s_median": float(np.median(latency)),
        "latency_s_p95": float(np.percentile(latency, 95)),
        "input_tokens_total": sum(p.input_tokens for p in predictions),
        "input_tokens_per_decision": sum(p.input_tokens for p in predictions) / len(predictions),
    }


def load_predictions(path: Path) -> list[RoutingPrediction]:
    return [
        RoutingPrediction.model_validate_json(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--backend", choices=list(BACKENDS), required=True)
    run_parser.add_argument("--out", type=Path, required=True)
    run_parser.add_argument("--limit", type=int, default=None)
    run_parser.add_argument("--labels", type=Path, default=None)
    score_parser = sub.add_parser("score")
    score_parser.add_argument("predictions", type=Path)
    score_parser.add_argument("--labels", type=Path, default=None)
    args = parser.parse_args()
    if args.command == "run":
        examples = load_examples(labels=args.labels)
        run(args.backend, examples[: args.limit], args.out)
    else:
        predictions = load_predictions(args.predictions)
        if args.labels is not None:
            override = {x.id: x.label for x in load_examples(labels=args.labels)}
            predictions = [p.model_copy(update={"label": override[p.id]}) for p in predictions]
        print(json.dumps(score(predictions), indent=2))


if __name__ == "__main__":
    main()
