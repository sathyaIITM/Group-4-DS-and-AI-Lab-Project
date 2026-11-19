"""Build routing data v2 on the frozen catalogue (T3 brief, task D2).

    python scripts/build_routing_v2.py --families 1300 --seed 21 \
        --candidates <dir with paraphrase.v1.jsonl, hard_cases.v1.jsonl, critic_verdicts.jsonl>

Steps:
1. Rule-generated records from configs/catalogue.toml (every published table), with the router
   state built as at serving: the tables a label depends on plus the best-ranked others from the
   Milestone 3 hybrid retriever (BM25 and bge-small-en-v1.5), top 4.
2. Model-written candidates (paraphrases and hard cases) are added only when the critic marked
   them `ok`. Their state and labels are kept; the question text is re-stamped with the current
   canonical text (guide 1.0, seven tool options), so training and serving use one wording.
   Candidates in the `train` split stay there; the rest keep their split.
3. data/splits/kev/<split>.v2.jsonl are written, the data checks are run, and the phase-1
   (domain only) files data/splits/kev_domain/<split>.v2.jsonl are derived.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyst.data.catalogue import load_catalogue  # noqa: E402
from analyst.data.kev_checks import run_checks  # noqa: E402
from analyst.data.kev_generate import generate, write_splits  # noqa: E402
from analyst.decisions import phase1  # noqa: E402
from analyst.decisions.kev_questions import (  # noqa: E402
    GUIDE_VERSION,
    QUESTIONS,
    KevRecord,
)

OUT = ROOT / "data" / "splits" / "kev"
DOMAIN_OUT = ROOT / "data" / "splits" / "kev_domain"
VERSION = 2
RANK_DEPTH = 10


def hybrid_ranker() -> Any:
    """Table names for a message, best first, from the serving retriever."""
    from analyst.retrieval.hybrid import HybridIndex, database_url_from_env
    from analyst.retrieval.knowledge import build_entries

    index = HybridIndex(build_entries(), database_url_from_env())
    index.build()
    cache: dict[str, list[str]] = {}

    def rank(message: str) -> list[str]:
        """Return the table ids the hybrid index ranks for a message, cached."""
        if message not in cache:
            hits = index.search(message, "table", RANK_DEPTH)
            cache[message] = [h.entry.dataset_id for h in hits if h.entry.dataset_id]
        return cache[message]

    return rank


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load the JSON objects of a JSONL file."""
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def current_lines(catalogue: Any) -> dict[str, str]:
    """Return the current catalogue line of every published table."""
    return {t.name: t.line for t in catalogue.real_tables()}


def refresh_catalogue(text: str, lines: dict[str, str]) -> str:
    """Candidate states were written against older catalogue lines; the router must see the
    lines it will see at serving. Each shown table keeps its position with its current line."""
    out = []
    for row in text.splitlines():
        number, _, rest = row.partition(". ")
        name = rest.split(":", 1)[0]
        out.append(f"{number}. {lines[name]}" if name in lines else row)
    return "\n".join(out)


def restamp(record: dict[str, Any], lines: dict[str, str]) -> KevRecord:
    """The candidate with the current question text and catalogue lines; state wording,
    labels and provenance unchanged."""
    questions = {}
    for name, (instructions, criteria) in QUESTIONS.items():
        label = record["questions"][name]["label"]
        if label not in criteria:
            raise ValueError(f"{record['_meta']['id']}: label {label!r} is no longer an option")
        questions[name] = {
            "type": "choice",
            "instructions": instructions,
            "criteria": criteria,
            "label": label,
        }
    meta = dict(record["_meta"])
    meta["guide_version"] = GUIDE_VERSION
    state = dict(record["state"])
    state["catalogue"] = refresh_catalogue(state["catalogue"], lines)
    return KevRecord.model_validate({"state": state, "questions": questions, "_meta": meta})


def candidates(directory: Path, lines: dict[str, str]) -> tuple[list[KevRecord], Counter[str]]:
    """Return the model-written records the critic kept, with counts per verdict."""
    verdicts = {v["id"]: v["verdict"] for v in read_jsonl(directory / "critic_verdicts.jsonl")}
    kept: list[KevRecord] = []
    counts: Counter[str] = Counter()
    for name in ("paraphrase.v1.jsonl", "hard_cases.v1.jsonl"):
        for record in read_jsonl(directory / name):
            verdict = verdicts.get(record["_meta"]["id"], "not_reviewed")
            counts[f"{name}:{verdict}"] += 1
            if verdict == "ok":
                kept.append(restamp(record, lines))
    return kept, counts


def main() -> None:
    """Build routing data v2."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--families", type=int, default=1300)
    parser.add_argument("--seed", type=int, default=21)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--no-ranker", action="store_true", help="random fill (tests only)")
    args = parser.parse_args()

    catalogue = load_catalogue(ROOT / "configs" / "catalogue.toml")
    ranker = None if args.no_ranker else hybrid_ranker()
    generated = generate(catalogue, args.families, args.seed, ranker)
    extra, counts = candidates(args.candidates, current_lines(catalogue))
    seen = {r.state.user_message.strip().lower() for r in generated}
    extra = [r for r in extra if r.state.user_message.strip().lower() not in seen]
    records = generated + extra
    paths = write_splits(records, OUT, VERSION)
    result = run_checks(OUT, VERSION)
    print("\n".join(result.lines))
    for split in phase1.SPLITS:
        n = phase1.convert_split(
            OUT / f"{split}.v{VERSION}.jsonl", DOMAIN_OUT / f"{split}.v{VERSION}.jsonl"
        )
        print(f"kev_domain/{split}.v{VERSION}.jsonl: {n} records")
    summary = {
        "families": args.families,
        "seed": args.seed,
        "generated": len(generated),
        "candidates_kept": len(extra),
        "candidate_verdicts": dict(counts),
        "splits": {s: len(p.read_text(encoding="utf-8").splitlines()) for s, p in paths.items()},
        "tool": Counter(r.tool for r in records),
        "domain": Counter(r.domain for r in records),
        "check_errors": result.errors,
    }
    print(json.dumps(summary, indent=2, default=dict))
    report = ROOT / "outputs" / "reports" / f"routing_build.v{VERSION}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, default=dict) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
