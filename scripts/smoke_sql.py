"""Smoke test of SQL generation on hand-built plans, executed on the published tables.

    python scripts/smoke_sql.py                      # plan only: nothing is sent
    python scripts/smoke_sql.py --yes --out outputs/reports/smoke_sql_<date>.json

The seven answerable questions of the Milestone 3 set (rp-01 to rp-07) get an
`InterpretationPlan` written by hand with the exact values of the published tables, standing in
for the resolver (T4) that will build plans in the agent. For each plan: `generate_sql` (prompt
`sql.v1`, model and thinking level from configs/model.yaml); the query runs through the
read-only guard on DuckDB; on a rejection or an error, one `repair_sql`. The check: the expected
figure is in the result rows, or, for the two questions that need a derivation (rp-04 mean,
rp-05 percentage change), it is computed from the rows as the agent's code would.

This checks the prompts against the real model; it is not an evaluation result.
Safety: nothing is sent without `--yes`; at most 3 calls per question (generate, retry,
repair) and MAX_CALLS in total; account, project, model and the worst-case cost are printed.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from analyst.contracts.common import IndicatorRef, PeriodWindow, Place
from analyst.contracts.intent import DerivationRequest
from analyst.contracts.plan import InterpretationPlan

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
MAX_CALLS = 30
INPUT_TOKENS_GUESS = 2000
TOLERANCE = 0.05

PLFS, IMD = "plfs_state_ur_usual_status", "imd_subdivision_monthly_rainfall"
NFHS, MANDI = "nfhs5_district_indicators", "mandi_daily_prices"
UNEMPLOYMENT_RATE = IndicatorRef(
    indicator_id="ur_usual_ps_ss", label="Unemployment rate (usual status)", unit="percent"
)
RAIN = IndicatorRef(indicator_id="rainfall_mm", label="Rainfall", unit="mm")
LITERATE = IndicatorRef(
    indicator_id="nfhs5_women_age_15_49_who_are_literate4_47d1ef18",
    label="Women age 15-49 who are literate",
    unit="percent",
)
MODAL = IndicatorRef(
    indicator_id="modal_price_inr_per_quintal", label="Modal price", unit="INR per quintal"
)


def survey_year(label: str) -> PeriodWindow:
    """Return the window of a July-June survey year label."""
    start = int(label[:4])
    return PeriodWindow(
        requested=label,
        type="survey_year",
        label=label,
        start=date(start, 7, 1),
        end=date(start + 1, 6, 30),
    )


def jjas(year: int) -> PeriodWindow:
    """Return the June-September monsoon window of a year."""
    return PeriodWindow(
        requested=f"monsoon {year}",
        type="season",
        label=f"{year}-JJAS",
        start=date(year, 6, 1),
        end=date(year, 9, 30),
    )


def place(name: str, level: str, code: str) -> Place:
    """Return an exactly matched place."""
    return Place(requested=name, level=level, code=code, name=name, match="exact")  # type: ignore[arg-type]


def plan(dataset: str, version: str, **fields: Any) -> InterpretationPlan:
    """Return a plan for a dataset with the given fields."""
    base: dict[str, Any] = {
        "dataset_id": dataset,
        "obs_table": f"obs_{dataset}",
        "dataset_version": version,
        "indicators": [],
        "places": [],
        "all_places_level": None,
        "periods": [],
        "categories": {},
        "operation": "lookup",
        "order": None,
        "limit": None,
        "derivations": [],
        "exclude_total_rows": False,
        "assumptions": [],
        "unresolved": [],
    }
    return InterpretationPlan(**(base | fields))


def cases() -> list[dict[str, Any]]:
    """Plans for rp-01 to rp-07, with the expected figure and how to check it."""
    tables = json.loads((PROCESSED / "catalogue.json").read_text())["tables"]
    ver = {t["dataset_id"]: t["dataset_version"] for t in tables}
    return [
        {
            "id": "rp-01",
            "expected": 25.7,
            "check": "in_rows",
            "plan": plan(
                PLFS,
                ver[PLFS],
                indicators=[UNEMPLOYMENT_RATE],
                all_places_level="state",
                periods=[survey_year("2019-20")],
                operation="ranking",
                order="desc",
                limit=1,
                exclude_total_rows=True,
            ),
        },
        {
            "id": "rp-02",
            "expected": 10.0,
            "check": "in_rows",
            "plan": plan(
                PLFS,
                ver[PLFS],
                indicators=[UNEMPLOYMENT_RATE],
                places=[place("Kerala", "state", "state:kerala")],
                periods=[survey_year("2019-20")],
            ),
        },
        {
            "id": "rp-03",
            "expected": 1856.5,
            "check": "in_rows",
            "plan": plan(
                IMD,
                ver[IMD],
                indicators=[RAIN],
                places=[place("Kerala", "subdivision", "subdivision:kerala")],
                periods=[jjas(2017)],
            ),
        },
        {
            "id": "rp-04",
            "expected": 1098.84,
            "check": "mean",
            "plan": plan(
                IMD,
                ver[IMD],
                indicators=[RAIN],
                places=[place("Orissa", "subdivision", "subdivision:orissa")],
                periods=[jjas(y) for y in range(1971, 2001)],
                operation="aggregate",
                derivations=[DerivationRequest(op="mean", args={})],
            ),
        },
        {
            "id": "rp-05",
            "expected": -31.67,
            "check": "pct_change",
            "plan": plan(
                PLFS,
                ver[PLFS],
                indicators=[UNEMPLOYMENT_RATE],
                places=[place("India", "national", "IN")],
                periods=[survey_year("2017-18"), survey_year("2021-22")],
                operation="change",
                derivations=[
                    DerivationRequest(
                        op="pct_change", args={"from_period": "2017-18", "to_period": "2021-22"}
                    )
                ],
            ),
        },
        {
            "id": "rp-06",
            "expected": 76.5,
            "check": "in_rows",
            "plan": plan(
                NFHS,
                ver[NFHS],
                indicators=[LITERATE],
                places=[place("Bihar", "state", "state:bihar")],
                all_places_level="district",
                operation="ranking",
                order="desc",
                limit=1,
                periods=[
                    PeriodWindow(
                        requested="latest",
                        type="survey_round",
                        label="2019-2021",
                        start=date(2019, 1, 1),
                        end=date(2021, 12, 31),
                    )
                ],
                exclude_total_rows=True,
            ),
        },
        {
            "id": "rp-07",
            "expected": 5650.0,
            "check": "in_rows",
            "plan": plan(
                MANDI,
                ver[MANDI],
                indicators=[MODAL],
                places=[place("Maharashtra", "state", "state:maharashtra")],
                all_places_level="market",
                categories={"commodity_name": ["Onion"]},
                operation="ranking",
                order="desc",
                limit=1,
                periods=[
                    PeriodWindow(
                        requested="latest",
                        type="date",
                        label="2026-10-29",
                        start=date(2026, 10, 29),
                        end=date(2026, 10, 29),
                    )
                ],
                exclude_total_rows=True,
            ),
        },
    ]


def numbers(rows: list[tuple[Any, ...]]) -> list[float]:
    """Return every number in the rows."""
    return [
        float(c) for r in rows for c in r if isinstance(c, int | float) and not isinstance(c, bool)
    ]


def value_column(columns: list[str], rows: list[tuple[Any, ...]]) -> list[float]:
    """Return the numbers of the value column."""
    i = columns.index("value") if "value" in columns else None
    return [float(r[i]) for r in rows if i is not None and r[i] is not None]


def judge(case: dict[str, Any], columns: list[str], rows: list[tuple[Any, ...]]) -> dict[str, Any]:
    """Score one smoke case against its expected figure."""
    expected = case["expected"]
    if case["check"] == "in_rows":
        found = any(abs(x - expected) <= TOLERANCE for x in numbers(rows))
        return {"ok": found, "observed": numbers(rows)[:6]}
    values = value_column(columns, rows)
    if case["check"] == "mean":
        observed = round(sum(values) / len(values), 2) if values else None
        return {
            "ok": observed is not None and abs(observed - expected) <= TOLERANCE,
            "observed": observed,
            "rows": len(values),
        }
    labels = (
        [str(r[columns.index("period_label")]) for r in rows] if "period_label" in columns else []
    )
    by_label = dict(zip(labels, values, strict=False))
    if {"2017-18", "2021-22"} <= set(by_label):
        observed = round((by_label["2021-22"] - by_label["2017-18"]) / by_label["2017-18"] * 100, 2)
        return {"ok": abs(observed - expected) <= TOLERANCE, "observed": observed}
    return {"ok": False, "observed": None, "note": "both periods not in the rows"}


def gcloud_value(key: str) -> str:
    """Return a gcloud configuration value."""
    result = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        ["gcloud", "config", "get-value", key],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.stdout.strip()


def main() -> int:
    """Run SQL generation on the hand-built smoke plans."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="send the calls (spends credit)")
    parser.add_argument("--only", nargs="+")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    from analyst.inference.llm import LlmClient, LlmError
    from analyst.inference.sqlgen import generate_sql, repair_sql
    from analyst.tools.sql_runner import ReadOnlyDatabase

    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", gcloud_value("project"))
    client = LlmClient.from_config(max_llm_calls=3)
    plans = [c for c in cases() if not args.only or c["id"] in set(args.only)]
    caps = {
        prompt: client.output_cap(prompt, client.thinking_level(prompt)) or 0
        for prompt in ("sql", "sql_repair")
    }
    price_in = client.price_per_mtok.get("input") or 0.0
    price_out = client.price_per_mtok.get("output") or 0.0
    worst = (
        len(plans)
        * (3 * INPUT_TOKENS_GUESS * price_in + (2 * caps["sql"] + caps["sql_repair"]) * price_out)
        / 1e6
    )
    print(f"account  {gcloud_value('account')}\nproject  {os.environ['GOOGLE_CLOUD_PROJECT']}")
    print(
        f"model    {client.model}  thinking sql={client.thinking_level('sql')} "
        f"repair={client.thinking_level('sql_repair')}"
    )
    print(f"questions {len(plans)}; at most {3 * len(plans)} calls; worst-case cost ${worst:.4f}")
    if 3 * len(plans) > MAX_CALLS:
        print(f"refused: more than {MAX_CALLS} calls")
        return 2
    if not args.yes:
        print("plan only: nothing sent (add --yes to send)")
        return 0

    tables = {f"obs_{c['plan'].dataset_id}" for c in plans}
    db = ReadOnlyDatabase({t: PROCESSED / f"{t}.parquet" for t in tables})
    rows_out, total = [], 0.0
    for case in plans:

        class Counter:
            llm_calls = 0

        plan: InterpretationPlan = case["plan"]
        schema = ", ".join(f"{c} {t}" for c, t in db.describe(plan.obs_table))
        row: dict[str, Any] = {"id": case["id"], "expected": case["expected"]}
        records: list[Any] = []
        try:
            draft, record = generate_sql(
                plan, schema, {"cards": [], "examples": []}, None, None, client, Counter()
            )
            records += [*record.earlier_attempts, record]
            row["sql"] = draft.sql
            try:
                columns, result = db.run(draft.sql)
            except Exception as error:  # rejected or failed: one bounded repair
                row["first_error"] = f"{type(error).__name__}: {str(error)[:160]}"
                draft, record = repair_sql(
                    draft, row["first_error"], schema, plan.obs_table, client, Counter()
                )
                records += [*record.earlier_attempts, record]
                row["repaired_sql"] = draft.sql
                columns, result = db.run(draft.sql)
            row |= judge(case, columns, result) | {"row_count": len(result)}
        except LlmError as error:
            records += error.records
            row |= {"ok": False, "error": str(error)[:200]}
        except Exception as error:  # record and continue
            row |= {"ok": False, "error": f"{type(error).__name__}: {str(error)[:200]}"}
        cost = sum(r.cost_usd_est or 0.0 for r in records)
        total += cost
        row["parse_errors"] = [r.parse_error for r in records if r.parse_error]
        row |= {
            "calls": len(records),
            "latency_ms": sum(r.latency_ms for r in records),
            "tokens_in": sum(r.tokens_in for r in records),
            "tokens_out": sum(r.tokens_out for r in records),
            "thinking_tokens": sum(r.reasoning_tokens or 0 for r in records),
            "cost_usd_est": round(cost, 6),
        }
        rows_out.append(row)
        print(json.dumps(row))
    ok = sum(1 for r in rows_out if r.get("ok"))
    print(f"expected figure reached: {ok} of {len(rows_out)}; total estimated cost ${total:.5f}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "model": client.model,
                    "ok": ok,
                    "questions": len(rows_out),
                    "total_cost_usd_est": total,
                    "rows": rows_out,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
