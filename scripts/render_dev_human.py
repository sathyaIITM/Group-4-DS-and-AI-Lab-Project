"""Render the dev_human items as router states, exactly as at serving time.

    python scripts/render_dev_human.py                      # items_rendered.jsonl and its hash
    python scripts/render_dev_human.py --out <path>

For each item in data/labels/dev_human_v1/items.jsonl the Milestone 3 hybrid retriever (BM25
and bge-small-en-v1.5) ranks the catalogue tables for the message; the top four lines of
configs/catalogue.toml, in rank order, form the state's catalogue; the context is rendered by
`kev_questions.render_context`; the state is built by `decisions.router.build_state` (the
function the router uses). The rendered file is what labellers read and what the models are
evaluated on; its SHA-256 is written next to it and recorded in data/MANIFEST.md.

Labels are judged against the catalogue shown in each state, so the state of an item holds the
tables the router would show. Items are not edited to make a table appear.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyst.data.catalogue import load_catalogue  # noqa: E402
from analyst.decisions.router import RouterContext, build_state  # noqa: E402

DIR = ROOT / "data" / "labels" / "dev_human_v1"
TOP_K = 4
DEPTH = 12


def main() -> None:
    """Render dev-human items with the state shown to labellers."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--items", type=Path, default=DIR / "items.jsonl")
    parser.add_argument("--out", type=Path, default=DIR / "items_rendered.jsonl")
    args = parser.parse_args()

    from analyst.retrieval.hybrid import HybridIndex, database_url_from_env
    from analyst.retrieval.knowledge import build_entries

    catalogue = load_catalogue(ROOT / "configs" / "catalogue.toml")
    lines = {t.name: t.line for t in catalogue.real_tables()}
    index = HybridIndex(build_entries(), database_url_from_env())
    index.build()

    rows: list[dict[str, Any]] = []
    for line in args.items.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        hits = index.search(item["message"], "table", DEPTH)
        ranked = [h.entry.dataset_id for h in hits if h.entry.dataset_id in lines]
        top = list(dict.fromkeys(ranked))[:TOP_K]
        context = item["context"]
        state = build_state(
            item["message"],
            RouterContext(
                has_result=bool(context.get("has_result")),
                prior_turn=context.get("prior_turn"),
                previous_tool=context.get("previous_tool"),
            ),
            [lines[name] for name in top],
        )
        rows.append({"id": item["id"], "state": state.model_dump(), "candidates": top})
    text = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    args.out.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    args.out.with_suffix(".sha256").write_text(f"{digest}  {args.out.name}\n", encoding="utf-8")
    print(f"{len(rows)} items rendered to {args.out}\nsha256 {digest}")


if __name__ == "__main__":
    main()
