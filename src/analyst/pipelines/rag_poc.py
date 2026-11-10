"""RAG proof of concept: question to released (or withheld) answer, through a LangGraph graph.

Retrieval supplies where to look and how to query; the figures come only from the executed
query. Nodes, in order:

    retrieve_tables     hybrid BM25 + bge-small (pgvector) ranking, top 4 tables
    retrieve_context    indicators of those tables, their convention cards, analysis SOP cards,
                        verified question/SQL examples
    extract_intent      hosted LLM: answer / clarify / decline, with dataset, indicators,
                        periods and places restricted to retrieved values
    check_coverage      code: the dataset, indicators, periods and places exist (no nearest
                        substitution); otherwise decline or clarify
    generate_sql        hosted LLM writes SQL over obs_<dataset> from intent, schema, cards,
                        examples
    execute             sqlglot read-only guard, DuckDB with timeout; one repair on failure
    check_result        code: non-empty, not truncated, no total row in a ranking, flags
    narrate             hosted LLM words the answer from the result rows only
    verify_and_release  code: every number in the narration must be a result cell (or appear
                        in the question, periods or definitions); otherwise withhold the
                        narration and release a templated answer, or abstain

Not included (stated in every trace): Kev routing, claim verification by Jev, the calibrated
confidence badge, conversation memory, and the Compose stack.

    python -m analyst.pipelines.rag_poc --out outputs/predictions/rag_poc.jsonl
"""

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any, TypedDict

import duckdb
from langgraph.graph import END, StateGraph

from analyst.inference.llm import LlmClient, LlmError
from analyst.retrieval.hybrid import Hit, HybridIndex, database_url_from_env
from analyst.retrieval.knowledge import ROOT, build_entries, obs_path
from analyst.tools.sql_runner import MAX_ROWS, ReadOnlyDatabase, SqlRejectedError, SqlTimeoutError

QUESTIONS = ROOT / "data" / "sample" / "rag_poc_questions.v0.jsonl"
TOP_TABLES = 4
INDICATORS_PER_TABLE = 10
ROWS_TO_LLM = 25
NOT_INCLUDED = [
    "Kev routing (tool and domain)",
    "claim verification by Jev and the calibrated confidence badge",
    "conversation memory and follow-ups",
    "Compose stack (UI, API, Caddy)",
]
CHART_RULES = {  # analysis SOP: chart by analysis type and row count (code, not the LLM)
    "lookup": lambda n: "none (single statistic)",
    "ranking": lambda n: "horizontal bar, sorted" if n > 3 else "none (table)",
    "change": lambda n: "none (single statistic)" if n <= 1 else "grouped bar",
    "trend": lambda n: "line",
    "aggregate": lambda n: "none (single statistic)" if n <= 1 else "bar",
    "comparison": lambda n: "bar" if n > 1 else "none (single statistic)",
}


class State(TypedDict, total=False):
    question: str
    tables: list[dict[str, Any]]
    indicators: list[dict[str, Any]]
    cards: list[dict[str, Any]]
    examples: list[dict[str, Any]]
    intent: dict[str, Any]
    coverage: dict[str, Any]
    sql: str
    sql_attempts: list[dict[str, Any]]
    columns: list[str]
    rows: list[list[Any]]
    checks: dict[str, Any]
    narration: str
    claims: dict[str, Any]
    outcome: str
    final_answer: str
    chart: str
    llm_calls: list[dict[str, Any]]
    timings: dict[str, float]
    error: str


def _hits(hits: list[Hit]) -> list[dict[str, Any]]:
    return [
        {
            "id": h.entry.id,
            "score": round(h.score, 4),
            "bm25_rank": h.bm25_rank,
            "vector_rank": h.vector_rank,
            **h.entry.payload,
        }
        for h in hits
    ]


def _numbers(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in re.findall(r"-?\d[\d,]*\.?\d*", text)]


class RagPipeline:
    def __init__(self, index: HybridIndex, llm: LlmClient) -> None:
        self.index = index
        self.llm = llm
        self.db = ReadOnlyDatabase(
            {
                f"obs_{e.dataset_id}": obs_path(e.dataset_id)
                for e in index.entries
                if e.kind == "table" and e.dataset_id
            }
        )
        self.domain_of = {
            e.dataset_id: e.payload["domain"]
            for e in index.entries
            if e.kind == "table" and e.dataset_id
        }
        self.cards_by_table: dict[str, list[dict[str, Any]]] = {}
        for e in index.entries:
            if e.kind == "card" and e.dataset_id:
                self.cards_by_table.setdefault(e.dataset_id, []).append(e.payload)
        self._labels = duckdb.connect(":memory:")
        self.graph = self._build_graph()

    # -- helpers ---------------------------------------------------------------------------
    def _llm(self, state: State, purpose: str, system: str, user: str) -> dict[str, Any]:
        reply, call = self.llm.json_call(purpose, system, user)
        state.setdefault("llm_calls", []).append(call.__dict__)
        return reply

    def _distinct(self, dataset_id: str, column: str) -> set[str]:
        if column not in {"indicator_id", "period_label", "geo_name", "geo_state"}:
            msg = f"column not allowed: {column}"
            raise ValueError(msg)
        sql = f"SELECT DISTINCT {column} FROM read_parquet(?)"  # noqa: S608 - whitelisted column
        rows = self._labels.execute(sql, [str(obs_path(dataset_id))]).fetchall()
        return {str(r[0]) for r in rows if r[0] is not None}

    @staticmethod
    def _timed(name: str, fn: Any) -> Any:
        def wrapper(state: State) -> State:
            start = time.perf_counter()
            update = fn(state) or {}
            timings = dict(state.get("timings", {}))
            timings[name] = round(time.perf_counter() - start, 3)
            update["timings"] = timings
            if "llm_calls" in state:
                update.setdefault("llm_calls", state["llm_calls"])
            return update

        return wrapper

    # -- nodes -----------------------------------------------------------------------------
    def retrieve_tables(self, state: State) -> State:
        hits = self.index.search(state["question"], "table", TOP_TABLES)
        return {"tables": _hits(hits)}

    def retrieve_context(self, state: State) -> State:
        q = state["question"]
        # A fixed quota per table: a small table sends all its indicators; a large one (NFHS-5,
        # 104 indicators) sends its best matches. A shared top-k let NFHS crowd out the rest.
        indicators: list[Hit] = []
        for ds in [t["dataset_id"] for t in state["tables"]]:
            own = [e for e in self.index.entries if e.kind == "indicator" and e.dataset_id == ds]
            if len(own) <= INDICATORS_PER_TABLE:
                indicators += [Hit(e, 0.0, None, None) for e in own]
            else:
                indicators += self.index.search(
                    q, "indicator", INDICATORS_PER_TABLE, dataset_ids={ds}
                )
        # A table's convention cards travel with the table (top two tables); analysis SOP
        # cards are general and are retrieved by similarity.
        cards = [
            c for t in state["tables"][:2] for c in self.cards_by_table.get(t["dataset_id"], [])
        ]
        sops = self.index.search(q, "card", 2, dataset_ids=set())
        examples = self.index.search(q, "example", 3)
        return {
            "indicators": _hits(indicators),
            "cards": cards + [h.entry.payload for h in sops],
            "examples": [h.entry.payload | {"score": round(h.score, 4)} for h in examples],
        }

    def extract_intent(self, state: State) -> State:
        tables = [
            {k: t[k] for k in ("dataset_id", "title", "geo_levels", "periods", "caveats")}
            for t in state["tables"]
        ]
        indicators = [
            {k: i[k] for k in ("dataset_id", "indicator_id", "label", "unit")}
            for i in state["indicators"]
        ]
        system = (
            "You read a user's question about Indian public data into a structured intent. "
            "You do not answer the question. Use only the tables, indicators and guidance below.\n"
            "Return JSON with keys: action ('answer', 'clarify' or 'decline'), reason, "
            "clarifying_question (string or null), dataset_id (one of the listed dataset_id "
            "values, or null), indicator_ids (list, each from the listed indicators of that "
            "dataset), analysis_type ('lookup', 'ranking', 'change', 'trend', 'aggregate' or "
            "'comparison'), periods (list of period labels exactly in the table's label format; "
            "for a range give the first and last label), places (list of place names as the "
            "table writes them, following the guidance cards; empty for all places), "
            "other_filters (object, for example commodity).\n"
            "Rules: choose 'decline' when no listed table holds the measure, the place level or "
            "the period asked for; never substitute a nearest period or a different measure. "
            "Choose 'clarify' only when the question is ambiguous or asks for something the "
            "table cannot express and a narrower question could be answered."
        )
        user = json.dumps(
            {
                "question": state["question"],
                "tables": tables,
                "indicators": indicators,
                "guidance": [c["body"] for c in state["cards"]],
            },
            ensure_ascii=False,
        )
        return {"intent": self._llm(state, "intent", system, user)}

    def check_coverage(self, state: State) -> State:
        intent = state["intent"]
        action = intent.get("action")
        if action != "answer":
            return {"coverage": {"status": action, "by": "intent", "reason": intent.get("reason")}}
        problems: list[str] = []
        ds = intent.get("dataset_id")
        if ds not in {t["dataset_id"] for t in state["tables"]}:
            return {
                "coverage": {
                    "status": "decline",
                    "by": "code",
                    "reason": f"dataset {ds!r} is not a retrieved table",
                }
            }
        indicator_ids = self._distinct(ds, "indicator_id")
        bad = [i for i in intent.get("indicator_ids") or [] if i not in indicator_ids]
        if bad or not intent.get("indicator_ids"):
            problems.append(f"unknown indicator {bad or '(none given)'}")
        labels = self._distinct(ds, "period_label")
        missing_periods = [p for p in intent.get("periods") or [] if p not in labels]
        if missing_periods:
            ordered = sorted(labels)
            problems.append(
                f"period {missing_periods} not in the table (covers {ordered[0]} to {ordered[-1]})"
            )
        places = self._distinct(ds, "geo_name") | self._distinct(ds, "geo_state")
        lower = {p.lower() for p in places}
        missing_places = [p for p in intent.get("places") or [] if p.lower() not in lower]
        if missing_places:
            return {
                "coverage": {
                    "status": "clarify",
                    "by": "code",
                    "reason": f"place {missing_places} not found in {ds}",
                }
            }
        if problems:
            return {"coverage": {"status": "decline", "by": "code", "reason": "; ".join(problems)}}
        return {"coverage": {"status": "covered", "by": "code", "reason": "all slots resolved"}}

    def generate_sql(self, state: State) -> State:
        intent = state["intent"]
        ds = intent["dataset_id"]
        table = f"obs_{ds}"
        schema = ", ".join(f"{c} {t}" for c, t in self.db.describe(table))
        examples = [{"question": e["question"], "sql": e["sql"]} for e in state["examples"]]
        attempts = state.get("sql_attempts", [])
        system = (
            "You write one DuckDB SQL query over the single table given. Return JSON with keys "
            "sql and computes (one line saying what the query returns). Rules: one read-only "
            "SELECT; filter by indicator_id; select geo_name (and geo_state where useful), "
            "period_label, value and unit, plus any computed column with a clear alias; follow "
            "the guidance cards and the analysis SOP; round computed values to 2 decimals; "
            "return at most 50 rows."
        )
        payload = {
            "question": state["question"],
            "intent": intent,
            "table": table,
            "schema": schema,
            "guidance": [c["body"] for c in state["cards"]],
            "verified_examples": examples,
        }
        if attempts:
            payload["previous_attempt"] = attempts[-1]
            payload["instruction"] = "The previous query failed; fix it."
        reply = self._llm(
            state,
            "sql" if not attempts else "sql_repair",
            system,
            json.dumps(payload, ensure_ascii=False),
        )
        return {"sql": str(reply.get("sql", "")).strip().rstrip(";")}

    def execute(self, state: State) -> State:
        attempts = list(state.get("sql_attempts", []))
        try:
            columns, rows = self.db.run(state["sql"])
        except (SqlRejectedError, SqlTimeoutError, duckdb.Error) as error:
            attempts.append({"sql": state["sql"], "error": f"{type(error).__name__}: {error}"})
            return {"sql_attempts": attempts, "columns": [], "rows": []}
        attempts.append({"sql": state["sql"], "error": None})
        return {"sql_attempts": attempts, "columns": columns, "rows": [list(r) for r in rows]}

    def check_result(self, state: State) -> State:
        rows, columns = state.get("rows", []), state.get("columns", [])
        failed = state["sql_attempts"][-1]["error"]
        checks: dict[str, Any] = {
            "executed": failed is None,
            "non_empty": bool(rows),
            "truncated": len(rows) >= MAX_ROWS,
        }
        if "geo_name" in columns and state["intent"].get("analysis_type") == "ranking":
            names = {str(r[columns.index("geo_name")]) for r in rows}
            checks["total_row_excluded"] = "India" not in names
        if "quality_flag" in columns:
            flags = {str(r[columns.index("quality_flag")]) for r in rows}
            checks["quality_flags"] = sorted(flags)
        checks["passed"] = (
            checks["executed"]
            and checks["non_empty"]
            and not checks["truncated"]
            and checks.get("total_row_excluded", True)
        )
        return {"checks": checks}

    def narrate(self, state: State) -> State:
        table = next(t for t in state["tables"] if t["dataset_id"] == state["intent"]["dataset_id"])
        system = (
            "You write the answer to a user's question from a query result. Use only the "
            "numbers in the result rows; do not compute new figures, do not add outside facts. "
            "Two or three sentences: the direct answer with units and period, the measure's "
            "definition, and any caveat from the guidance that applies. Return JSON with key "
            "answer."
        )
        payload = {
            "question": state["question"],
            "columns": state["columns"],
            "rows": state["rows"][:ROWS_TO_LLM],
            "computes": state["intent"],
            "source": {k: table[k] for k in ("title", "publisher", "source_table")},
            "guidance": [c["body"] for c in state["cards"]],
        }
        reply = self._llm(
            state, "narration", system, json.dumps(payload, ensure_ascii=False, default=str)
        )
        return {"narration": str(reply.get("answer", ""))}

    def verify_and_release(self, state: State) -> State:
        allowed: list[float] = []
        for row in state["rows"]:
            for cell in row:
                allowed += [float(cell)] if isinstance(cell, int | float) else _numbers(str(cell))
        context = " ".join(
            [
                state["question"],
                json.dumps(state["intent"]),
                " ".join(i["label"] + " " + i["unit"] for i in state["indicators"]),
                " ".join(c["body"] for c in state["cards"]),
            ]
        )
        allowed += _numbers(context)
        claimed = _numbers(state["narration"])
        unsupported = [
            n
            for n in claimed
            if not any(abs(n - a) <= 0.051 or abs(abs(n) - abs(a)) <= 0.051 for a in allowed)
        ]
        chart = CHART_RULES.get(state["intent"].get("analysis_type", ""), lambda n: "none")(
            len(state["rows"])
        )
        claims = {"numbers_in_narration": claimed, "unsupported": unsupported}
        if not unsupported:
            return {
                "claims": claims,
                "outcome": "answered",
                "final_answer": state["narration"],
                "chart": chart,
            }
        head = ", ".join(
            f"{c} = {v}" for c, v in zip(state["columns"], state["rows"][0], strict=True)
        )
        return {
            "claims": claims,
            "outcome": "answered_template",
            "chart": chart,
            "final_answer": f"Narration withheld (unsupported figures {unsupported}). "
            f"First result row: {head}.",
        }

    def finalize_non_answer(self, state: State) -> State:
        cov = state["coverage"]
        if cov["status"] == "clarify":
            question = state["intent"].get("clarifying_question") or cov["reason"]
            return {"outcome": "clarify", "final_answer": question}
        if cov["status"] == "decline":
            return {
                "outcome": "decline",
                "final_answer": f"Not answered from the catalogue: {cov['reason']}",
            }
        return {
            "outcome": "abstain",
            "final_answer": "The query could not be executed and checked; no answer is "
            f"released. Last error: {state['sql_attempts'][-1]['error']}"
            if state.get("sql_attempts")
            else "No answer released.",
        }

    # -- graph -----------------------------------------------------------------------------
    def _build_graph(self) -> Any:
        g = StateGraph(State)
        for name in (
            "retrieve_tables",
            "retrieve_context",
            "extract_intent",
            "check_coverage",
            "generate_sql",
            "execute",
            "check_result",
            "narrate",
            "verify_and_release",
            "finalize_non_answer",
        ):
            g.add_node(name, self._timed(name, getattr(self, name)))
        g.set_entry_point("retrieve_tables")
        g.add_edge("retrieve_tables", "retrieve_context")
        g.add_edge("retrieve_context", "extract_intent")
        g.add_edge("extract_intent", "check_coverage")
        g.add_conditional_edges(
            "check_coverage",
            lambda s: (
                "generate_sql" if s["coverage"]["status"] == "covered" else "finalize_non_answer"
            ),
        )
        g.add_edge("generate_sql", "execute")
        g.add_conditional_edges(  # one repair attempt on a failed or rejected query
            "execute",
            lambda s: (
                "generate_sql"
                if s["sql_attempts"][-1]["error"] and len(s["sql_attempts"]) < 2
                else "check_result"
            ),
        )
        g.add_conditional_edges(
            "check_result",
            lambda s: "narrate" if s["checks"]["passed"] else "finalize_non_answer",
        )
        g.add_edge("narrate", "verify_and_release")
        g.add_edge("verify_and_release", END)
        g.add_edge("finalize_non_answer", END)
        return g.compile()

    def run(self, question: str) -> State:
        start = time.perf_counter()
        try:
            state: State = self.graph.invoke({"question": question, "llm_calls": []})
        except LlmError as error:
            return {"question": question, "outcome": "error", "error": str(error)}
        state["timings"] = {
            **state.get("timings", {}),
            "total": round(time.perf_counter() - start, 3),
        }
        return state


# -- scoring -------------------------------------------------------------------------------
def score(case: dict[str, Any], state: State) -> dict[str, Any]:
    """End-to-end success: the right action and, for answers, the expected figures and places
    in the executed result with a released (supported) answer."""
    outcome = state.get("outcome", "error")
    expected = case["expected_action"]
    if expected != "answer":
        return {"success": outcome == expected, "why": f"expected {expected}, got {outcome}"}
    if outcome not in {"answered", "answered_template"}:
        return {"success": False, "why": f"expected an answer, got {outcome}"}
    cells = [c for row in state.get("rows", []) for c in row]
    nums = [float(c) for c in cells if isinstance(c, int | float)]
    text = " ".join(str(c) for c in cells).lower()
    values_ok = all(
        any(abs(abs(n) - abs(v)) <= 0.01 for n in nums) for v in case.get("expected_values", [])
    )
    entities_ok = all(e.lower() in text for e in case.get("expected_entities", []))
    released = outcome == "answered"
    return {
        "success": values_ok and entities_ok and released,
        "why": f"values {'ok' if values_ok else 'MISSING'}, entities "
        f"{'ok' if entities_ok else 'MISSING'}, narration "
        f"{'released' if released else 'withheld'}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/predictions/rag_poc.jsonl")
    parser.add_argument("--only", nargs="*", help="case ids to run")
    args = parser.parse_args()

    t0 = time.perf_counter()
    index = HybridIndex(build_entries(), database_url_from_env())
    backend = index.build()
    print(
        f"index: {len(index.entries)} entries, backend {backend}, {time.perf_counter() - t0:.1f} s"
    )
    pipeline = RagPipeline(index, LlmClient.from_env())

    cases = [json.loads(line) for line in args.questions.read_text().splitlines() if line.strip()]
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only)]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    results = []
    with args.out.open("w", encoding="utf-8") as handle:
        for case in cases:
            state = pipeline.run(case["question"])
            verdict = score(case, state)
            calls = state.get("llm_calls", [])
            record = {
                "case_id": case["id"],
                "model": pipeline.llm.model,
                "retrieval_backend": backend,
                **verdict,
                "expected_action": case["expected_action"],
                "llm_call_count": len(calls),
                "tokens": sum(c["prompt_tokens"] + c["completion_tokens"] for c in calls),
                "not_included": NOT_INCLUDED,
                **state,
            }
            if "per day" in state.get("error", ""):
                print(f"{case['id']}: daily request quota of the model reached; run stopped")
                break
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            results.append(record)
            total = state.get("timings", {}).get("total", 0.0)
            print(
                f"{case['id']}: {'OK ' if verdict['success'] else 'MISS'} "
                f"{state.get('outcome', 'error'):<17} {total:>6.2f} s "
                f"{len(calls)} calls | {verdict['why']}"
            )
    ok = sum(r["success"] for r in results)
    times = sorted(r.get("timings", {}).get("total", 0.0) for r in results)
    print(
        f"\nend-to-end success {ok}/{len(results)}; median time "
        f"{times[len(times) // 2]:.2f} s; LLM calls {sum(r['llm_call_count'] for r in results)}; "
        f"tokens {sum(r['tokens'] for r in results)}; output {args.out}"
    )


if __name__ == "__main__":
    main()
