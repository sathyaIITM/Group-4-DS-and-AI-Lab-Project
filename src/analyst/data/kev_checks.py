"""Quality checks for Kev record files (Kev data curation plan, Sections 8.2-8.3).

Checks: canonical question text and labels, state length, option balance, group leakage
across splits, exact duplicates and conflicting labels, near-duplicate messages across
splits, and a keyword-only shortcut baseline (TF-IDF and logistic regression).

Usage (from the repository root):
    python -m analyst.data.kev_checks data/splits/kev --version 1 \
        --report outputs/reports/kev_checks.v1.md [--write]
"""

import argparse
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from analyst.decisions.kev_questions import QUESTIONS, STATE_CHAR_LIMIT, KevRecord

SPLITS = ("train", "calibration", "dev_synthetic")
MIN_OPTION_SHARE = 0.05
NEAR_DUP_JACCARD = 0.8
SHINGLE = 5


def normalise(text: str, map_digits: bool = True) -> str:
    """Lowercase, map digits to 0, drop punctuation, collapse whitespace.

    Digit mapping suits grouping and near-duplicate search; exact-state checks keep digits,
    because a changed year can change the label (an out-of-range period is declined).
    """
    text = text.casefold()
    if map_digits:
        text = re.sub(r"\d", "0", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def shingles(text: str) -> frozenset[str]:
    padded = f" {normalise(text)} "
    if len(padded) <= SHINGLE:
        return frozenset({padded})
    return frozenset(padded[i : i + SHINGLE] for i in range(len(padded) - SHINGLE + 1))


def state_key(record: KevRecord) -> str:
    """Identity of a state: the set of catalogue lines, the context and the message."""
    lines = sorted(re.sub(r"^\d+\.\s*", "", x) for x in record.state.catalogue.splitlines())
    message = normalise(record.state.user_message, map_digits=False)
    return "\n".join([*lines, record.state.context, message])


def load_split(path: Path) -> tuple[list[KevRecord], list[str]]:
    records, errors = [], []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(KevRecord.model_validate_json(line))
        except ValueError as error:
            errors.append(f"{path.name}:{number}: {str(error).splitlines()[0]}")
    return records, errors


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    drop: set[str] = field(default_factory=set)  # record ids removed by --write


def check_lengths_and_balance(splits: dict[str, list[KevRecord]], result: CheckResult) -> None:
    result.lines.append("## Sizes, state length and option balance\n")
    result.lines.append("| Split | Records | Groups | Longest state (chars) | Over limit |")
    result.lines.append("| --- | --- | --- | --- | --- |")
    for name, records in splits.items():
        lengths = [r.state.rendered_length() for r in records] or [0]
        over = sum(x > STATE_CHAR_LIMIT for x in lengths)
        groups = len({r.meta.group_id for r in records})
        result.lines.append(f"| {name} | {len(records)} | {groups} | {max(lengths)} | {over} |")
        if over:
            result.errors.append(f"{name}: {over} states exceed {STATE_CHAR_LIMIT} characters")
    for question, (_, options) in QUESTIONS.items():
        result.lines.append(f"\n`{question}` share per option:\n")
        result.lines.append("| Option | " + " | ".join(splits) + " |")
        result.lines.append("| --- |" + " --- |" * len(splits))
        for option in options:
            cells = []
            for name, records in splits.items():
                share = sum(r.questions[question].label == option for r in records) / max(
                    len(records), 1
                )
                cells.append(f"{share:.1%}")
                if share < MIN_OPTION_SHARE:
                    result.errors.append(f"{name}: {question}={option} below 5% ({share:.1%})")
            result.lines.append(f"| {option} | " + " | ".join(cells) + " |")


def check_leakage_and_duplicates(splits: dict[str, list[KevRecord]], result: CheckResult) -> None:
    result.lines.append("\n## Group leakage and duplicates\n")
    owners: dict[str, set[str]] = defaultdict(set)
    for name, records in splits.items():
        for r in records:
            owners[r.meta.group_id].add(name)
    leaked = [g for g, names in owners.items() if len(names) > 1]
    result.lines.append(f"- Groups in more than one split: {len(leaked)}")
    if leaked:
        result.errors.append(f"{len(leaked)} groups span two splits")

    by_state: dict[str, list[tuple[str, KevRecord]]] = defaultdict(list)
    for name, records in splits.items():
        for r in records:
            by_state[state_key(r)].append((name, r))
    redundant = conflicts = 0
    for entries in by_state.values():
        if len(entries) < 2:
            continue
        labels = {(r.tool, r.domain) for _, r in entries}
        if len(labels) > 1:
            conflicts += 1
            result.errors.append(
                "conflicting labels on one state: "
                + ", ".join(f"{r.meta.id}={r.tool}/{r.domain}" for _, r in entries)
            )
            continue
        for _, r in entries[1:]:
            redundant += 1
            result.drop.add(r.meta.id)
    result.lines.append(f"- Exact duplicate states (same labels), extra copies: {redundant}")
    result.lines.append(f"- Identical states with conflicting labels: {conflicts}")

    train = [(r, shingles(r.state.user_message)) for r in splits.get("train", [])]
    pairs: list[tuple[KevRecord, KevRecord, float]] = []
    for name in SPLITS[1:]:
        for r in splits.get(name, []):
            mine = shingles(r.state.user_message)
            for other, theirs in train:
                small, large = sorted((len(mine), len(theirs)))
                if small < NEAR_DUP_JACCARD * large:
                    continue
                jaccard = len(mine & theirs) / len(mine | theirs)
                if jaccard >= NEAR_DUP_JACCARD:
                    pairs.append((r, other, jaccard))
                    result.drop.add(r.meta.id)
                    break
    result.lines.append(
        f"- Evaluation-split messages within Jaccard {NEAR_DUP_JACCARD} of a training message "
        f"(character {SHINGLE}-grams after normalisation): {len(pairs)}"
    )
    for r, other, jaccard in pairs[:10]:
        result.lines.append(
            f"  - {r.meta.id} ({r.meta.split}) ~ {other.meta.id} (train), J={jaccard:.2f}: "
            f'"{r.state.user_message}" / "{other.state.user_message}"'
        )


def check_shortcuts(splits: dict[str, list[KevRecord]], result: CheckResult) -> None:
    """Keyword-only baseline: high accuracy from the message words alone means shortcuts."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, f1_score

    train, dev = splits.get("train", []), splits.get("dev_synthetic", [])
    result.lines.append("\n## Shortcut baseline (TF-IDF word 1-2 grams, logistic regression)\n")
    if not train or not dev:
        result.lines.append("- Skipped: needs train and dev_synthetic.")
        return
    result.lines.append(
        "Trained on train, scored on dev_synthetic. Rule-generated text shares templates "
        "across splits, so this score is an upper bound on lexical shortcuts; the decisive run "
        "is on dev-human once it exists.\n"
    )
    result.lines.append("| Question | Input | Accuracy | Macro-F1 | Majority-class accuracy |")
    result.lines.append("| --- | --- | --- | --- | --- |")
    for question in QUESTIONS:
        y_train = [r.questions[question].label for r in train]
        y_dev = [r.questions[question].label for r in dev]
        majority = Counter(y_train).most_common(1)[0][0]
        base = sum(y == majority for y in y_dev) / len(y_dev)
        for input_name in ("message", "message + context"):

            def text(r: KevRecord, name: str = input_name) -> str:
                if name == "message":
                    return r.state.user_message
                return f"{r.state.context} {r.state.user_message}"

            vectoriser = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
            x_train = vectoriser.fit_transform([text(r) for r in train])
            model = LogisticRegression(max_iter=2000).fit(x_train, y_train)
            predicted = model.predict(vectoriser.transform([text(r) for r in dev]))
            accuracy = accuracy_score(y_dev, predicted)
            macro = f1_score(y_dev, predicted, average="macro")
            result.lines.append(
                f"| {question} | {input_name} | {accuracy:.3f} | {macro:.3f} | {base:.3f} |"
            )
            if question == "tool" and input_name == "message":
                vocab = vectoriser.get_feature_names_out()
                result.lines.append("")
                for label, weights in zip(model.classes_, model.coef_, strict=True):
                    top = ", ".join(vocab[i] for i in weights.argsort()[::-1][:6])
                    result.lines.append(f"  - top words for `{label}`: {top}")
                result.lines.append("")


def run_checks(directory: Path, version: int, shortcuts: bool = True) -> CheckResult:
    result = CheckResult()
    splits: dict[str, list[KevRecord]] = {}
    for name in SPLITS:
        path = directory / f"{name}.v{version}.jsonl"
        if not path.exists():
            result.errors.append(f"missing {path}")
            continue
        splits[name], errors = load_split(path)
        result.errors.extend(errors)
    result.lines.append(f"# Kev data checks, version {version}\n")
    check_lengths_and_balance(splits, result)
    check_leakage_and_duplicates(splits, result)
    if shortcuts:
        check_shortcuts(splits, result)
    result.lines.append("\n## Problems\n")
    result.lines.extend(f"- {e}" for e in result.errors or ["None."])
    return result


def write_without(directory: Path, version: int, drop: set[str]) -> int:
    removed = 0
    for name in SPLITS:
        path = directory / f"{name}.v{version}.jsonl"
        if not path.exists():
            continue
        kept = []
        for line in path.read_text().splitlines():
            if line.strip() and KevRecord.model_validate_json(line).meta.id in drop:
                removed += 1
                continue
            kept.append(line)
        path.write_text("\n".join(kept) + "\n")
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Quality checks for Kev record files.")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--no-shortcuts", action="store_true")
    parser.add_argument(
        "--write",
        action="store_true",
        help="remove extra exact duplicates and evaluation-split near-duplicates in place",
    )
    args = parser.parse_args()
    result = run_checks(args.directory, args.version, shortcuts=not args.no_shortcuts)
    report = "\n".join(result.lines) + "\n"
    print(report)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report)
    if args.write and result.drop:
        print(f"removed {write_without(args.directory, args.version, result.drop)} records")


if __name__ == "__main__":
    main()
