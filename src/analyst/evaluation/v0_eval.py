"""v0 baseline: a hosted LLM writes DuckDB SQL for each question, nothing else.

The model sees only the table schemas and the question. Its SQL passes the
read-only guard and is scored by comparing the executed result with the result of
the reference SQL. A question marked unanswerable is correct only if the model
replies DECLINE.

Usage (from the repository root, with LLM_API_KEY, LLM_MODEL and LLM_BASE_URL set):
    python -m analyst.evaluation.v0_eval run --out outputs/week1/v0_<model>.jsonl
    python -m analyst.evaluation.v0_eval score outputs/week1/v0_<model>.jsonl
"""

import argparse
import json
import os
import re
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import sqlglot
from pydantic import BaseModel
from sqlglot import exp

from analyst.tools.sql_runner import ReadOnlyDatabase, SqlRejectedError, SqlTimeoutError

QUESTIONS = Path("data/sample/v0_questions.jsonl")
TABLES = {
    "imd_subdivision_monthly_rainfall": Path(
        "data/processed/imd_subdivision_monthly_rainfall.parquet"
    ),
    "plfs_state_ur_usual_status": Path("data/processed/plfs_state_ur_usual_status.parquet"),
}
DECLINE = "DECLINE"
SYSTEM_PROMPT = (
    "You answer questions about Indian public data by writing one DuckDB SQL query.\n"
    "Rules: output a single read-only SELECT statement inside a ```sql fence and nothing else. "
    "Use only the tables below. If the question cannot be answered from these tables, "
    "output exactly DECLINE instead of SQL.\n\n"
)
ROUND = 2


class Question(BaseModel):
    id: str
    question: str
    reference_sql: str | None = None
    answerable: bool


class Outcome(BaseModel):
    id: str
    status: (
        str  # correct | wrong_result | wrongly_declined | answered_unanswerable | rejected | error
    )
    sql: str | None = None
    detail: str = ""
    latency_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0


def open_database() -> ReadOnlyDatabase:
    return ReadOnlyDatabase(TABLES)


def schema_text(database: ReadOnlyDatabase) -> str:
    """Column names and types for every table, plus a small row sample."""
    parts = []
    for name in sorted(database.table_names):
        columns = ", ".join(f"{col} {kind}" for col, kind in database.describe(name))
        _, rows = database.run(f"SELECT * FROM {name} LIMIT 3")  # noqa: S608
        parts.append(f"Table {name}\nColumns: {columns}\nSample rows: {rows}\n")
    return "\n".join(parts)


def chat(question: str, schema: str) -> tuple[str, int, int]:
    """One call to an OpenAI-compatible chat completions endpoint."""
    base = os.environ["LLM_BASE_URL"].rstrip("/")
    response = httpx.post(
        f"{base}/chat/completions",
        headers={
            "Authorization": f"Bearer {os.environ['LLM_API_KEY']}",
            "User-Agent": "india-analyst-agent/0.0",
        },
        json={
            "model": os.environ["LLM_MODEL"],
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT + schema},
                {"role": "user", "content": question},
            ],
        },
        timeout=120.0,
    )
    response.raise_for_status()
    body = response.json()
    usage = body.get("usage", {})
    return (
        body["choices"][0]["message"]["content"],
        int(usage.get("prompt_tokens", 0)),
        int(usage.get("completion_tokens", 0)),
    )


def extract_sql(reply: str) -> str | None:
    """The SQL in the reply, or None when the model declined."""
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", reply, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip().rstrip(";")
    if reply.strip().upper().startswith(DECLINE):
        return None
    return reply.strip().rstrip(";")


def normalise(rows: list[tuple[Any, ...]]) -> list[tuple[str, ...]]:
    def cell(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, float):
            return f"{round(value, ROUND):.{ROUND}f}"
        return str(value)

    return [tuple(cell(v) for v in row) for row in rows]


def same_result(
    reference_sql: str, got: list[tuple[Any, ...]], expected: list[tuple[Any, ...]]
) -> bool:
    """Compare rows ignoring column names; order matters only if the reference sorts."""
    ordered = sqlglot.parse_one(reference_sql, read="duckdb").find(exp.Order) is not None
    a, b = normalise(got), normalise(expected)
    return a == b if ordered else Counter(a) == Counter(b)


def judge(
    question: Question, reply: str, database: ReadOnlyDatabase
) -> tuple[str, str | None, str]:
    """Return (status, sql, detail) for one model reply."""
    sql = extract_sql(reply)
    if sql is None:
        return ("correct" if not question.answerable else "wrongly_declined"), None, ""
    if not question.answerable:
        return "answered_unanswerable", sql, ""
    if question.reference_sql is None:
        msg = f"{question.id} is answerable but has no reference SQL"
        raise ValueError(msg)
    try:
        _, got = database.run(sql)
    except (SqlRejectedError, SqlTimeoutError) as error:
        return "rejected", sql, str(error)[:200]
    except Exception as error:
        return "error", sql, f"{type(error).__name__}: {str(error)[:200]}"
    _, expected = database.run(question.reference_sql)
    return (
        ("correct" if same_result(question.reference_sql, got, expected) else "wrong_result"),
        sql,
        "",
    )


def run(out: Path, ask: Callable[[str, str], tuple[str, int, int]] = chat) -> None:
    """Query the model for every question, appending outcomes to `out` (resumable)."""
    database = open_database()
    schema = schema_text(database)
    questions = [
        Question.model_validate_json(line) for line in QUESTIONS.read_text().splitlines() if line
    ]
    done = (
        {json.loads(x)["id"] for x in out.read_text().splitlines() if x} if out.exists() else set()
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as handle:
        for question in questions:
            if question.id in done:
                continue
            started = time.perf_counter()
            reply, prompt_tokens, completion_tokens = ask(question.question, schema)
            latency = time.perf_counter() - started
            status, sql, detail = judge(question, reply, database)
            outcome = Outcome(
                id=question.id,
                status=status,
                sql=sql,
                detail=detail,
                latency_s=latency,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            handle.write(outcome.model_dump_json() + "\n")
            handle.flush()


def score(path: Path) -> dict[str, Any]:
    outcomes = [Outcome.model_validate_json(x) for x in path.read_text().splitlines() if x]
    counts = Counter(o.status for o in outcomes)
    latencies = sorted(o.latency_s for o in outcomes)
    return {
        "n": len(outcomes),
        "execution_accuracy": counts["correct"] / len(outcomes),
        "status_counts": dict(counts),
        "latency_s_median": latencies[len(latencies) // 2],
        "prompt_tokens": sum(o.prompt_tokens for o in outcomes),
        "completion_tokens": sum(o.completion_tokens for o in outcomes),
        "failures": {o.id: o.status for o in outcomes if o.status != "correct"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--out", type=Path, required=True)
    score_parser = sub.add_parser("score")
    score_parser.add_argument("outcomes", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        run(args.out)
    else:
        print(json.dumps(score(args.outcomes), indent=2))


if __name__ == "__main__":
    main()
