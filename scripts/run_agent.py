from __future__ import annotations
import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any
from analyst.agents.graph import build_graph
from analyst.agents.runlog import RunLogger
from analyst.agents.state import AnalystState, RunConfig

def run_one(question: str, *, version: str = "v0", conversation_id: str | None = None,
            experiment: str | None = None, eval_set: str | None = None, member: str | None = None) -> dict[str, Any]:
    config = RunConfig.from_files(version)
    initial = AnalystState(
        run_id=str(uuid.uuid4()), conversation_id=conversation_id or str(uuid.uuid4()),
        question=question, config=config
    )
    graph = build_graph()
    result = graph.invoke(initial.model_dump())
    RunLogger().write_state(result)
    result["_cli_metadata"] = {"experiment": experiment, "eval_set": eval_set, "member": member}
    return result

def main() -> int:
    parser = argparse.ArgumentParser(description="Run the analyst agent")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--question")
    source.add_argument("--file", type=Path)
    parser.add_argument("--version", default="v0", choices=[f"v{i}" for i in range(7)])
    parser.add_argument("--experiment")
    parser.add_argument("--eval-set")
    parser.add_argument("--member")
    args = parser.parse_args()
    questions = [args.question] if args.question else [
        json.loads(line)["question"] for line in args.file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    failed = False
    for question in questions:
        try:
            result = run_one(question, version=args.version, experiment=args.experiment,
                             eval_set=args.eval_set, member=args.member)
            print(json.dumps({
                "run_id": result.get("run_id"), "outcome": result.get("outcome"),
                "cause": result.get("outcome_cause"), "response": result.get("response_text", ""),
            }, default=str))
        except Exception as error:  # CLI must preserve evaluation progress; failure is an outcome.
            failed = True
            print(json.dumps({"outcome": "failed", "error_type": type(error).__name__}), file=sys.stderr)
    # A failed agent run is a valid recorded evaluation outcome, not a CLI crash.
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
