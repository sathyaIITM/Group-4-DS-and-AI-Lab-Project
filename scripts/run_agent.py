"""Run the analyst agent on one question or a file of questions.

    python scripts/run_agent.py --question "Show monthly rainfall in Kerala" --version v0
    python scripts/run_agent.py --file questions.jsonl --version v2 --eval-set e2e_dev
    python scripts/run_agent.py --question "..." --llm live --yes   # spends cloud credit

The run log is written once, by the `finalize_response` node. Each question gives one JSON line
on stdout (run_id, outcome, cause, response); an error is printed to stderr as one JSON line,
with the traceback only under --debug.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from analyst.agents.graph import invoke_graph
from analyst.agents.state import AnalystState, RunConfig


def run_one(
    question: str,
    *,
    version: str = "v0",
    conversation_id: str | None = None,
    config: RunConfig | None = None,
    meta: dict[str, str | None] | None = None,
    nodes: dict[str, Callable[[AnalystState], dict[str, Any]]] | None = None,
) -> AnalystState:
    state = AnalystState(
        run_id=str(uuid.uuid4()),
        conversation_id=conversation_id or str(uuid.uuid4()),
        question=question,
        config=config or RunConfig.from_files(version),
        meta=meta or {},
    )
    return invoke_graph(state, overrides=nodes)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the analyst agent")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--question")
    source.add_argument("--file", type=Path)
    parser.add_argument("--version", default="v0", choices=[f"v{i}" for i in range(7)])
    parser.add_argument("--experiment", help="free label such as v2_run1")
    parser.add_argument("--eval-set", help="e2e_dev, e2e_test, adhoc, ...")
    parser.add_argument("--member", help="T1 to T4")
    parser.add_argument(
        "--llm",
        choices=["stub", "live"],
        default="stub",
        help="stub: no model call (default); live: T3 nodes on the hosted model",
    )
    parser.add_argument("--yes", action="store_true", help="confirm that a live run spends credit")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--save-chart",
        nargs="?",
        const=Path("outputs/answers"),
        type=Path,
        metavar="DIR",
        help="write one HTML page per run (answer, chart, rows, SQL) to DIR "
        "(default outputs/answers)",
    )
    args = parser.parse_args()
    nodes = None
    if args.llm == "live":
        if not args.yes:
            parser.error("--llm live calls the hosted model and spends cloud credit; add --yes")
        from analyst.agents.t3_nodes import live_t3_nodes

        nodes = live_t3_nodes(args.version)
    if args.question:
        questions = [args.question]
    else:
        lines = args.file.read_text(encoding="utf-8").splitlines()
        questions = [json.loads(line)["question"] for line in lines if line.strip()]
    for question in questions:
        try:
            meta = {"experiment": args.experiment, "eval_set": args.eval_set, "member": args.member}
            state = run_one(question, version=args.version, meta=meta, nodes=nodes)
            record: dict[str, Any] = {
                "run_id": state.run_id,
                "outcome": state.outcome,
                "cause": state.outcome_cause,
                "response": state.response_text,
            }
            if args.save_chart is not None:
                from analyst.agents.answer_page import save_answer_page

                record["page"] = str(save_answer_page(state, args.save_chart))
            print(json.dumps(record, default=str))
        except Exception as error:  # a failed run is an evaluation outcome, not a CLI crash
            print(
                json.dumps(
                    {"outcome": "failed", "error_type": type(error).__name__, "error": str(error)}
                ),
                file=sys.stderr,
            )
            if args.debug:
                traceback.print_exc()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
