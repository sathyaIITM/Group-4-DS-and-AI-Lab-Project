"""Optimise the intent prompt with GEPA on dev items: agent version v3 (Milestone 5).

    python scripts/optimise_prompts.py                     # plan only: items, split, budget
    python scripts/optimise_prompts.py --yes               # live run (spends cloud credit)

Dev sets only: `data/eval/e2e_dev.v1.jsonl`, `e2e_dev_extra.v1.jsonl` and, when present,
`e2e_dev_m5.v1.jsonl`. An item whose id is in a test file is refused. Items must be validated
(`gold_version` 2) unless `--allow-unvalidated` is given. Follow-ups and describe/search items
are left out (`analyst.models.prompt_optimisation.eligible`).

The live run uses the default model tier for the intent calls (the agent's model) and the large
tier for GEPA's reflection. `--max-metric-calls` caps the item evaluations (one intent call
each); the report gives the measured cost. Outputs:

- `outputs/reports/gepa_v3.json`: inputs, split, budget, every candidate's validation score,
  the chosen candidate and the measured cost;
- `configs/prompts/intent_gepa.v1.md`: the best candidate, written only when it scores above the
  starting prompt on the validation items. It is pinned to v3 and v4 by hand, after review,
  in `configs/model.yaml` (`prompt_pins`).
"""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyst.inference.prompts import PromptRegistry, load_prompt  # noqa: E402
from analyst.models import prompt_optimisation as po  # noqa: E402

DEV_SETS = [
    ROOT / "data/eval/e2e_dev.v1.jsonl",
    ROOT / "data/eval/e2e_dev_extra.v1.jsonl",
    ROOT / "data/eval/e2e_dev_m5.v1.jsonl",
]
TEST_SETS = [ROOT / "data/eval/e2e_test.v1.jsonl", ROOT / "data/eval/e2e_test_ext.v1.jsonl"]
OUT_PROMPT = ROOT / "configs/prompts/intent_gepa.v1.md"
REPORT = ROOT / "outputs/reports/gepa_v3.json"
# Estimates for the plan only (USD per call); the report gives the measured cost.
EST_INTENT_CALL = 0.004
EST_REFLECTION_CALL = 0.03


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file; a missing file gives no rows."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def sha256(path: Path) -> str | None:
    """SHA-256 of a file, or None when it is missing."""
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main() -> int:
    """Plan or run the GEPA optimisation of the intent prompt."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--sets", type=Path, nargs="+", default=DEV_SETS)
    parser.add_argument("--version", default="v3", help="agent version whose retrieval is used")
    parser.add_argument("--max-metric-calls", type=int, default=300)
    parser.add_argument("--minibatch", type=int, default=4, help="items per reflection step")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--allow-unvalidated", action="store_true")
    parser.add_argument("--yes", action="store_true", help="run live (spends cloud credit)")
    args = parser.parse_args()

    test_ids = {str(i["id"]) for path in TEST_SETS for i in read_jsonl(path)}
    items = [i for path in args.sets for i in read_jsonl(path)]
    leaked = sorted({str(i["id"]) for i in items} & test_ids)
    if leaked:
        raise SystemExit(f"test items in the optimisation sets: {leaked[:5]}")
    if not args.allow_unvalidated:
        unvalidated = [i["id"] for i in items if i.get("gold_version") != 2]
        if unvalidated:
            raise SystemExit(
                f"{len(unvalidated)} items are not validated (gold_version 2), for example "
                f"{unvalidated[:3]}; validate them or pass --allow-unvalidated"
            )
    eligible = [i for i in items if po.eligible(i)]
    train, val = po.split_items(eligible, seed=args.seed)
    base = PromptRegistry().get("intent")
    seed_text, _ = po.split_system(base.system)
    reflections = max(1, args.max_metric_calls // (2 * args.minibatch))
    estimate = args.max_metric_calls * EST_INTENT_CALL + reflections * EST_REFLECTION_CALL
    plan = {
        "sets": {str(p.relative_to(ROOT)): sha256(p) for p in args.sets},
        "items": len(items),
        "eligible": len(eligible),
        "train": [i["id"] for i in train],
        "val": [i["id"] for i in val],
        "base_prompt": {"id": base.prompt_id, "sha256": base.sha256},
        "max_metric_calls": args.max_metric_calls,
        "minibatch": args.minibatch,
        "seed": args.seed,
        "estimated_cost_usd": round(estimate, 2),
    }
    print(
        json.dumps({k: v if not isinstance(v, list) else len(v) for k, v in plan.items()}, indent=2)
    )
    if not args.yes:
        print("plan only: no model call made (add --yes to run; estimate above is not a quote)")
        return 0

    import gepa

    from analyst.inference.llm import LlmClient

    reflection_spent: list[float] = []
    adapter = po.IntentAdapter(base=base, make_llm=LlmClient.from_config, version=args.version)
    started = datetime.now(UTC)
    result = gepa.optimize(
        seed_candidate={po.COMPONENT: seed_text},
        trainset=train,
        valset=val,
        adapter=adapter,
        reflection_lm=po.reflection_lm(LlmClient.from_config(tier="large"), reflection_spent),
        max_metric_calls=args.max_metric_calls,
        reflection_minibatch_size=args.minibatch,
        seed=args.seed,
        run_dir=str(ROOT / "outputs/gepa_v3"),
        display_progress_bar=False,
    )
    scores = list(result.val_aggregate_scores)
    best = max(range(len(scores)), key=lambda i: scores[i])
    improved = best != 0 and scores[best] > scores[0]
    written = None
    if improved:
        text = po.candidate_prompt(base, result.candidates[best][po.COMPONENT]).text
        OUT_PROMPT.write_text(text, encoding="utf-8")
        written = {
            "path": str(OUT_PROMPT.relative_to(ROOT)),
            "sha256": load_prompt(OUT_PROMPT).sha256,
        }
    report = {
        **plan,
        "started_utc": started.isoformat(timespec="seconds"),
        "ended_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "versions": {"gepa": package_version("gepa"), "dspy": package_version("dspy")},
        "models": {
            "intent": LlmClient.from_config().model,
            "reflection": LlmClient.from_config(tier="large").model,
        },
        "total_metric_calls": result.total_metric_calls,
        "candidates": len(result.candidates),
        "val_scores": scores,
        "seed_val_score": scores[0],
        "best_index": best,
        "best_val_score": scores[best],
        "improved": improved,
        "written_prompt": written,
        "cost_usd": {
            "intent_calls": round(adapter.spent_usd, 4),
            "reflection": round(sum(reflection_spent), 4),
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {k: report[k] for k in ("seed_val_score", "best_val_score", "improved", "cost_usd")},
            indent=2,
        )
    )
    print("report:", REPORT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
