"""Domain decision on `stress_v1` (80 hard and unfamiliar messages): build the split and score.

    python scripts/score_stress_v1.py build      # data/splits/kev_domain/stress_v1.v1.jsonl
    KEV_BASE_URL=... python -m analyst.evaluation.domain_eval run --split stress_v1 --out ...
    python scripts/score_stress_v1.py score      # outputs/reports/score_domain_stress_v1.json

`build` joins the rendered router states (`data/labels/stress_v1/items_rendered.jsonl`) with T3's
intended labels (`data/labels/stress_v1/intended_labels_T3.csv`, sealed before any model run;
SHA-256 in the set's README). `score` applies each system's temperature fitted on the calibration
split, reports accuracy with a bootstrap interval (10,000 resamples, seed 0), ECE (10 bins), the
result per message category, and the cascade at the escalation threshold of
`configs/inference.yaml`.
The threshold is not refitted here: `stress_v1` is an evaluation set only.
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyst.evaluation.domain_eval import apply_temperature  # noqa: E402

LABELS = (
    "labour", "agriculture", "rainfall", "prices_economy", "health", "other", "multiple",
    "unspecified",
)  # fmt: skip
SET_DIR = ROOT / "data" / "labels" / "stress_v1"
SPLIT = ROOT / "data" / "splits" / "kev_domain" / "stress_v1.v1.jsonl"
PRED = ROOT / "outputs" / "predictions"
REPORTS = ROOT / "outputs" / "reports"
# name, predictions on stress_v1, report holding the temperature fitted on calibration
SYSTEMS = (
    ("Kev ep3_s2", "domain_ep3_s2_stress_v1.jsonl", "score_domain_ep3_s2.json"),
    ("Jev", "domain_jev_stress_v1.jsonl", "score_domain_jev_v2.json"),
)


def build() -> None:
    """Write the stress split in the layout of `dev_human` (one domain question per record)."""
    template = json.loads(
        (ROOT / "data" / "splits" / "kev_domain" / "dev_human.v1.jsonl").open().readline()
    )["questions"]["domain"]
    with (SET_DIR / "intended_labels_T3.csv").open(newline="", encoding="utf-8") as handle:
        labels = {row["item_id"]: row for row in csv.DictReader(handle)}
    rows = []
    for line in (SET_DIR / "items_rendered.jsonl").read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        label = labels[item["id"]]
        question = {**template, "label": label["domain"]}
        meta = {"id": item["id"], "label_source": "T3 intended (single author)"}
        rows.append(
            {
                "state": item["state"],
                "questions": {"domain": question},
                "_meta": {**meta, "split": "stress_v1", "category": label["category"]},
            }
        )
    SPLIT.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    print(f"wrote {len(rows)} records to {SPLIT.relative_to(ROOT)}")


def _ece(probs: np.ndarray, truth: np.ndarray, bins: int = 10) -> float:
    confidence, predicted = probs.max(axis=1), probs.argmax(axis=1)
    total = 0.0
    for low in np.linspace(0, 1, bins, endpoint=False):
        mask = (confidence > low) & (confidence <= low + 1 / bins)
        if mask.any():
            gap = abs((predicted[mask] == truth[mask]).mean() - confidence[mask].mean())
            total += float(mask.mean() * gap)
    return total


def _load(name: str, report: str) -> tuple[list[dict], np.ndarray, np.ndarray]:
    rows = [json.loads(x) for x in (PRED / name).read_text(encoding="utf-8").splitlines() if x]
    truth = np.array([LABELS.index(r["label"]) for r in rows])
    raw = np.array([[float(r["probabilities"].get(k, 0.0)) for k in LABELS] for r in rows])
    temperature = float(json.loads((REPORTS / report).read_text())["fitted_temperature"])
    return rows, truth, apply_temperature(raw, temperature)


def score() -> None:
    """Score each system and the cascade; write the report."""
    category = {
        json.loads(x)["_meta"]["id"]: json.loads(x)["_meta"]["category"]
        for x in SPLIT.read_text(encoding="utf-8").splitlines()
        if x
    }
    loaded = {name: _load(f, r) for name, f, r in SYSTEMS}
    result: dict = {}
    for name, (rows, truth, probs) in loaded.items():
        correct = probs.argmax(axis=1) == truth
        rng = np.random.default_rng(0)
        boot = [correct[rng.integers(0, len(correct), len(correct))].mean() for _ in range(10000)]
        per: dict[str, list[bool]] = defaultdict(list)
        for row, ok in zip(rows, correct, strict=True):
            per[category[row["id"]]].append(bool(ok))
        result[name] = {
            "n": len(rows),
            "accuracy": round(float(correct.mean()), 4),
            "ci95": [round(float(np.percentile(boot, q)), 4) for q in (2.5, 97.5)],
            "ece": round(_ece(probs, truth), 4),
            "mean_confidence": round(float(probs.max(axis=1).mean()), 4),
            "per_category": {k: f"{sum(v)}/{len(v)}" for k, v in sorted(per.items())},
        }
    band = yaml.safe_load((ROOT / "configs" / "inference.yaml").read_text())["escalation"]
    threshold = float(band["domain"]["high"])
    _, truth, kev = loaded["Kev ep3_s2"]
    _, _, jev = loaded["Jev"]
    escalate = kev.max(axis=1) < threshold
    final = np.where(escalate, jev.argmax(axis=1), kev.argmax(axis=1))
    kev_ok = kev.argmax(axis=1) == truth
    result["cascade"] = {
        "threshold": threshold,
        "escalated": int(escalate.sum()),
        "accuracy": round(float((final == truth).mean()), 4),
        "kev_confidence_correct": round(float(kev.max(axis=1)[kev_ok].mean()), 4),
        "kev_confidence_wrong": round(float(kev.max(axis=1)[~kev_ok].mean()), 4),
    }
    note = "stress_v1 (80 items); labels: T3 intended (single author, sealed before any run)"
    out = REPORTS / "score_domain_stress_v1.json"
    out.write_text(json.dumps({"note": note, "systems": result}, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    {"build": build, "score": score}[sys.argv[1] if len(sys.argv) > 1 else "score"]()
