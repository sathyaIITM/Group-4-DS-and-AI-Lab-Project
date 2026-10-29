"""Ingest model-written Kev data: parse replies, build candidate records, prepare critic batches.

Replies come back as pasted text, so the reader tolerates missing newlines, code fences, stray
characters between objects and one known fault (unescaped quotes inside a free-text field).
Candidate records keep `label_source` ("paraphrase" or "teacher"), the batch and the model's
own ambiguity flag, and are never merged into the rule-labelled splits until they pass the
critic and human review.

Usage (from the repository root):
    python -m analyst.data.kev_ingest build --returns ../docs/kev_prompts/returns \
        --out data/splits/kev_candidates
    python -m analyst.data.kev_ingest critic-batches --candidates data/splits/kev_candidates \
        --template ../docs/kev_prompts/templates/B5_critic.md --out ../docs/kev_prompts/packs
"""

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from analyst.data.catalogue import CATALOGUE_PATH, load_catalogue
from analyst.data.kev_checks import normalise, shingles
from analyst.data.kev_generate import split_of
from analyst.decisions.kev_questions import (
    DOMAIN_OPTIONS,
    TOOL_OPTIONS,
    KevRecord,
    KevState,
    RecordMeta,
    build_record,
    render_context,
)

DECODER = json.JSONDecoder()
FREE_TEXT_TAIL = re.compile(r'("question_for_human": ")(.*)(", "axes")', re.S)
NEAR_DUP_JACCARD = 0.8
SEED = 31
PACK_CHARS = 38_000  # keeps a pasted prompt under the chat input limit seen on 2026-10-24


def read_objects(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Every JSON object in a pasted reply; the second value lists what could not be read."""
    text = re.sub(r"^```[a-z]*\s*$", "", path.read_text(encoding="utf-8"), flags=re.M)
    objects: list[dict[str, Any]] = []
    problems: list[str] = []
    i = 0
    while i < len(text):
        while i < len(text) and text[i] in " \t\r\n,\\":
            i += 1
        if i >= len(text):
            break
        try:
            obj, i = DECODER.raw_decode(text, i)
        except json.JSONDecodeError as error:
            end = text.find("\n{", i + 1)
            repaired = (
                _repair(text[i : end if end != -1 else len(text)]) if text[i] == "{" else None
            )
            if repaired is not None:
                objects.append(repaired)
                problems.append(f"{path.name}: repaired quotes in object near offset {i}")
                i = end + 1 if end != -1 else len(text)
                continue
            if text[i] == "{":
                problems.append(f"{path.name}: unreadable object near offset {i}: {error.msg}")
            following = text.find("{", i + 1)
            i = following if following != -1 else len(text)
            continue
        if isinstance(obj, dict):
            objects.append(obj)
    return objects, problems


def _repair(chunk: str) -> dict[str, Any] | None:
    """Escape bare double quotes inside `question_for_human`, the one fault seen so far."""
    match = FREE_TEXT_TAIL.search(chunk)
    if not match:
        return None
    inner = match.group(2).replace('\\"', '"').replace('"', '\\"')
    fixed = chunk[: match.start(2)] + inner + chunk[match.end(2) :]
    try:
        value = json.loads(fixed.strip())
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def load_split(path: Path) -> dict[str, dict[str, Any]]:
    rows = (json.loads(line) for line in path.read_text().splitlines() if line.strip())
    return {r["_meta"]["id"]: r for r in rows}


def state_catalogue(tables_shown: list[str], lines: dict[str, str]) -> str:
    return "\n".join(f"{i}. {lines[name]}" for i, name in enumerate(tables_shown, start=1))


def candidate_ok(item: dict[str, Any]) -> list[str]:
    errors = []
    if item.get("tool") not in TOOL_OPTIONS:
        errors.append(f"bad tool {item.get('tool')!r}")
    if item.get("domain") not in DOMAIN_OPTIONS:
        errors.append(f"bad domain {item.get('domain')!r}")
    return errors


def build_paraphrases(
    objects: list[dict[str, Any]], train: dict[str, dict[str, Any]]
) -> tuple[list[KevRecord], list[str]]:
    records: list[KevRecord] = []
    notes: list[str] = []
    seen = {normalise(r["state"]["user_message"]) for r in train.values()}
    for obj in objects:
        source = train.get(obj["source_id"])
        if source is None:
            notes.append(f"unknown source {obj['source_id']}")
            continue
        for k, text in enumerate(obj["paraphrases"], start=1):
            key = normalise(text)
            if not text.strip() or key in seen:
                notes.append(f"duplicate or empty paraphrase of {obj['source_id']}")
                continue
            seen.add(key)
            meta = {
                **source["_meta"],
                "id": f"para-{obj['source_id']}-{k}",
                "label_source": "paraphrase",
                "tags": [*source["_meta"]["tags"], f"source:{obj['source_id']}"],
            }
            data = {
                "state": {**source["state"], "user_message": text.strip()},
                "questions": source["questions"],
                "_meta": meta,
            }
            records.append(KevRecord.model_validate(data))
    return records, notes


def build_hard_cases(
    objects: list[dict[str, Any]],
    lines: dict[str, str],
    seen: set[str],
    batch_of: dict[str, str],
) -> tuple[list[KevRecord], list[dict[str, Any]], list[str]]:
    records: list[KevRecord] = []
    questions: list[dict[str, Any]] = []
    notes: list[str] = []
    for item in objects:
        errors = candidate_ok(item)
        shown = [t for t in item.get("tables_shown", []) if t in lines]
        if not shown:
            errors.append("no valid table shown")
        key = normalise(str(item.get("user_message", "")))
        if key in seen:
            errors.append("duplicate message")
        if errors:
            notes.append(f"{item.get('id')}: {', '.join(errors)}")
            continue
        seen.add(key)
        group = f"teacher:{hashlib.sha256(key.encode()).hexdigest()[:12]}"
        state = KevState(
            catalogue=state_catalogue(shown, lines),
            context=render_context(
                bool(item["has_result"]), item.get("prior_turn"), item.get("previous_tool")
            ),
            user_message=item["user_message"].strip(),
        )
        tags = [str(a) for a in item.get("axes", [])]
        if item.get("ambiguous"):
            tags.append("model_ambiguous")
        if item.get("open_question"):
            tags.append(f"open:{item['open_question']}")
        meta = RecordMeta(
            id=str(item["id"]),
            group_id=group,
            split=split_of(group),
            label_source="teacher",
            tool_rule=str(item.get("tool_rule", "NONE")),
            domain_rule=str(item.get("domain_rule", "NONE")),
            family=batch_of[str(item["id"])],
            template_id="teacher",
            tags=tags,
            has_result=bool(item["has_result"]),
            generator="b3-hard-cases",
            seed=SEED,
        )
        records.append(build_record(state, item["tool"], item["domain"], meta))
        if item.get("question_for_human"):
            questions.append({"id": item["id"], "question": item["question_for_human"]})
    return records, questions, notes


def near_duplicates(records: list[KevRecord], train: list[dict[str, Any]]) -> set[str]:
    """Candidate ids whose message is within Jaccard 0.8 of a training message."""
    reference = [shingles(r["state"]["user_message"]) for r in train]
    flagged = set()
    for r in records:
        mine = shingles(r.state.user_message)
        for theirs in reference:
            small, large = sorted((len(mine), len(theirs)))
            if small >= NEAR_DUP_JACCARD * large and (
                len(mine & theirs) / len(mine | theirs) >= NEAR_DUP_JACCARD
            ):
                flagged.add(r.meta.id)
                break
    return flagged


def write_jsonl(path: Path, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + ("\n" if rows else ""))


def compare_relabels(
    returns: Path, train: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """B4: two independent relabels of rule-labelled items against the rule labels."""
    votes: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for path in sorted(returns.glob("B4_*")):
        model = path.stem.rsplit("_", 1)[-1]
        for obj in read_objects(path)[0]:
            votes[obj["id"]][model] = obj
    rows: list[dict[str, Any]] = []
    stats: Counter[str] = Counter()
    for item_id, by_model in votes.items():
        record = train.get(item_id)
        if record is None or len(by_model) < 2:
            continue
        rule_tool = record["questions"]["tool"]["label"]
        rule_domain = record["questions"]["domain"]["label"]
        tools = {m: v["tool"] for m, v in by_model.items()}
        domains = {m: v["domain"] for m, v in by_model.items()}
        stats["items"] += 1
        stats["tool_all_agree"] += len({rule_tool, *tools.values()}) == 1
        stats["domain_all_agree"] += len({rule_domain, *domains.values()}) == 1
        for m in by_model:
            stats[f"tool_{m}_matches_rule"] += tools[m] == rule_tool
            stats[f"domain_{m}_matches_rule"] += domains[m] == rule_domain
        if len({rule_tool, *tools.values()}) > 1 or len({rule_domain, *domains.values()}) > 1:
            rows.append(
                {
                    "id": item_id,
                    "message": record["state"]["user_message"],
                    "catalogue_tables": record["state"]["catalogue"].count("\n") + 1,
                    "context": record["state"]["context"][:60],
                    "rule": [rule_tool, rule_domain, record["_meta"]["tool_rule"]],
                    "models": {
                        m: [v["tool"], v["domain"], v.get("note")] for m, v in by_model.items()
                    },
                }
            )
    return rows, {k: float(v) for k, v in stats.items()}


def build(returns: Path, train_path: Path, out: Path, catalogue_path: Path) -> None:
    train = load_split(train_path)
    tables = load_catalogue(catalogue_path).real_tables()
    lines = {t.name: t.line for t in tables}
    problems: list[str] = []

    objects: list[dict[str, Any]] = []
    for path in sorted(returns.glob("B2_*")):
        found, bad = read_objects(path)
        objects.extend(found)
        problems.extend(bad)
    paraphrases, notes = build_paraphrases(objects, train)
    problems.extend(notes)

    hard: list[dict[str, Any]] = []
    batch_of: dict[str, str] = {}
    for path in sorted(returns.glob("B3_*")):
        found, bad = read_objects(path)
        hard.extend(found)
        problems.extend(bad)
        batch_of.update({str(o.get("id")): path.stem for o in found})
    seen = {normalise(r["state"]["user_message"]) for r in train.values()}
    seen |= {normalise(r.state.user_message) for r in paraphrases}
    cases, questions, notes = build_hard_cases(hard, lines, seen, batch_of)
    problems.extend(notes)

    reference = list(train.values())
    flagged = near_duplicates([*paraphrases, *cases], reference)
    paraphrases = [r for r in paraphrases if r.meta.id not in flagged]
    cases = [r for r in cases if r.meta.id not in flagged]

    write_jsonl(out / "paraphrase.v1.jsonl", [r.to_json() for r in paraphrases])
    write_jsonl(out / "hard_cases.v1.jsonl", [r.to_json() for r in cases])
    write_jsonl(out / "questions_for_human.jsonl", [json.dumps(q) for q in questions])
    disagreements, stats = compare_relabels(returns, train)
    write_jsonl(out / "relabel_disagreements.jsonl", [json.dumps(d) for d in disagreements])
    write_jsonl(out / "ingest_problems.txt", problems)
    print(f"paraphrases: {len(paraphrases)} (dropped {len(flagged)} near-duplicates in total)")
    print(f"hard cases: {len(cases)}, with {len(questions)} questions for a human")
    print(f"relabel comparison: {json.dumps(stats)}")
    print(f"problems logged: {len(problems)}")


RISK_TAGS = {
    "multi_place", "lacking_group", "year_type", "no_measure", "follow_up", "no_national_row",
    "absent_breakdown", "out_of_range", "context_domain", "cross_measure", "absent_table",
}  # fmt: skip


def critic_item(r: dict[str, Any]) -> str:
    shown = [
        re.sub(r"^\d+\.\s*", "", line).split(":", 1)[0]
        for line in r["state"]["catalogue"].splitlines()
    ]
    return json.dumps(
        {
            "id": r["_meta"]["id"],
            "tables_shown": shown,
            "context": r["state"]["context"],
            "user_message": r["state"]["user_message"],
            "tool": r["questions"]["tool"]["label"],
            "domain": r["questions"]["domain"]["label"],
            "tool_rule": r["_meta"]["tool_rule"],
            "domain_rule": r["_meta"]["domain_rule"],
        },
        ensure_ascii=False,
    )


def reviewed_ids(returns: Path | None) -> set[str]:
    if returns is None:
        return set()
    return {
        str(o["id"])
        for path in returns.glob("B5_*")
        for o in read_objects(path)[0]
        if "verdict" in o
    }


def critic_selection(
    candidates: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Hard cases, the paraphrases sent to the critic, and all paraphrases (seeded)."""
    rng = random.Random(SEED)  # noqa: S311 - reproducible sampling, not security
    cases = [json.loads(x) for x in (candidates / "hard_cases.v1.jsonl").read_text().splitlines()]
    paras = [json.loads(x) for x in (candidates / "paraphrase.v1.jsonl").read_text().splitlines()]
    risky = [p for p in paras if RISK_TAGS & set(p["_meta"]["tags"])]
    rest = [p for p in paras if p not in risky]
    sampled = risky + rng.sample(rest, k=min(len(rest), len(rest) // 4))
    return cases, sampled, paras


def critic_batches(
    candidates: Path,
    template: Path,
    guide: Path,
    out: Path,
    returns: Path | None = None,
    max_chars: int = PACK_CHARS,
) -> None:
    cases, sampled, paras = critic_selection(candidates)
    done = reviewed_ids(returns)
    ordered = [r for r in [*cases, *sampled] if r["_meta"]["id"] not in done]
    tables = "\n".join(f"- {t.line}" for t in load_catalogue().real_tables())
    guide_text = guide.read_text().split("\n## 5.")[0].rstrip() + "\n"
    head = template.read_text().replace("{{GUIDE}}", guide_text).replace("{{TABLES}}", tables)
    for old in out.glob("B5_critic_*.md"):
        old.unlink()
    batches: list[list[dict[str, Any]]] = [[]]
    size = len(head)
    for r in ordered:
        length = len(critic_item(r)) + 1
        if batches[-1] and size + length > max_chars:
            batches.append([])
            size = len(head)
        batches[-1].append(r)
        size += length
    for b, batch in enumerate(batches, start=1):
        body = head.replace("{{ITEMS}}", "\n".join(critic_item(r) for r in batch))
        (out / f"B5_critic_{b:02d}.md").write_text(body)
        print(f"  B5_critic_{b:02d}.md: {len(batch)} items, {len(body)} characters")
    print(
        f"{len(ordered)} items to review ({len(done)} already reviewed, {len(cases)} hard cases, "
        f"{len(sampled)} of {len(paras)} paraphrases) -> {len(batches)} critic packs"
    )


def critic_merge(candidates: Path, returns: Path) -> None:
    """Merge critic verdicts into one table, check coverage and list what a human must settle."""
    cases, sampled, _ = critic_selection(candidates)
    expected = {r["_meta"]["id"]: r for r in [*cases, *sampled]}
    verdicts: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    problems: list[str] = []
    for path in sorted(returns.glob("B5_*")):
        objects, bad = read_objects(path)
        problems.extend(bad)
        for o in objects:
            if "verdict" not in o or "id" not in o:
                problems.append(f"{path.name}: object without id and verdict")
                continue
            if str(o["id"]) in verdicts:
                duplicates.append(str(o["id"]))
            verdicts[str(o["id"])] = {**o, "_file": path.stem}
    missing = sorted(set(expected) - set(verdicts))
    unknown = sorted(set(verdicts) - set(expected))
    by_kind: dict[str, Counter[str]] = {"hard_case": Counter(), "paraphrase": Counter()}
    issues: Counter[str] = Counter()
    for item_id, v in verdicts.items():
        if item_id not in expected:
            continue
        kind = (
            "hard_case" if expected[item_id]["_meta"]["label_source"] == "teacher" else "paraphrase"
        )
        by_kind[kind][str(v["verdict"])] += 1
        issues.update(v.get("issues", []))
    print(
        f"expected {len(expected)}, received {len(verdicts)}, missing {len(missing)}, "
        f"unknown {len(unknown)}, duplicate ids {len(duplicates)}"
    )
    for kind, counts in by_kind.items():
        print(f"  {kind}: {dict(counts)}")
    print(f"  issue types: {dict(issues)}")
    write_jsonl(candidates / "critic_missing.txt", missing)
    flagged = [
        {
            "id": i,
            "message": expected[i]["state"]["user_message"],
            "label": [
                expected[i]["questions"]["tool"]["label"],
                expected[i]["questions"]["domain"]["label"],
            ],
            "rule": expected[i]["_meta"]["tool_rule"],
            "verdict": v["verdict"],
            "issues": v.get("issues", []),
            "suggested": [v.get("suggested_tool"), v.get("suggested_domain")],
            "comment": v.get("comment"),
        }
        for i, v in sorted(verdicts.items())
        if i in expected and v["verdict"] != "ok"
    ]
    write_jsonl(
        candidates / "critic_flagged.jsonl", [json.dumps(f, ensure_ascii=False) for f in flagged]
    )
    questions = [
        {
            "id": i,
            "question": v["question_for_human"],
            "message": expected[i]["state"]["user_message"],
        }
        for i, v in sorted(verdicts.items())
        if i in expected and v.get("question_for_human")
    ]
    write_jsonl(
        candidates / "critic_questions.jsonl",
        [json.dumps(q, ensure_ascii=False) for q in questions],
    )
    write_jsonl(
        candidates / "critic_verdicts.jsonl",
        [json.dumps(v, ensure_ascii=False) for _, v in sorted(verdicts.items())],
    )
    print(
        f"flagged {len(flagged)}, questions for a human {len(questions)}, "
        f"reader problems {len(problems)}"
    )
    for p in problems[:10]:
        print("  ", p)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest model-written Kev data.")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--returns", type=Path, required=True)
    b.add_argument("--train", type=Path, default=Path("data/splits/kev/train.v1.jsonl"))
    b.add_argument("--catalogue", type=Path, default=CATALOGUE_PATH)
    b.add_argument("--out", type=Path, default=Path("data/splits/kev_candidates"))
    c = sub.add_parser("critic-batches")
    c.add_argument("--candidates", type=Path, default=Path("data/splits/kev_candidates"))
    c.add_argument("--template", type=Path, required=True)
    c.add_argument("--guide", type=Path, default=Path("docs/labelling_guide_v1.md"))
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--returns", type=Path, help="skip items that already have a verdict here")
    c.add_argument("--max-chars", type=int, default=PACK_CHARS)
    m = sub.add_parser("critic-merge")
    m.add_argument("--candidates", type=Path, default=Path("data/splits/kev_candidates"))
    m.add_argument("--returns", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "critic-merge":
        critic_merge(args.candidates, args.returns)
    elif args.command == "build":
        build(args.returns, args.train, args.out, args.catalogue)
    else:
        critic_batches(
            args.candidates, args.template, args.guide, args.out, args.returns, args.max_chars
        )


if __name__ == "__main__":
    main()
