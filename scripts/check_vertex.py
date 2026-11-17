"""Check Gemini access on Vertex AI: one small call per thinking level for one tier.

    python scripts/check_vertex.py                      # plan only: prints what would be sent
    python scripts/check_vertex.py --yes                # sends the calls (spends credit)
    python scripts/check_vertex.py --tier small --levels minimal medium --yes
    python scripts/check_vertex.py --model gemini-3.8-flash --price-in 0.75 --price-out 3.75

For each call it prints the requested and served model, the thinking level, latency, input and
output tokens, thinking tokens (when reported), the finish reason, whether the reply was valid
JSON, and the estimated cost. The output cap is set as in the agent (`max_output_tokens.sql`),
so the run shows whether thinking tokens count against the cap.

Safety: nothing is sent without `--yes`; at most MAX_CALLS calls per run; the project comes from
`GOOGLE_CLOUD_PROJECT` or the active gcloud configuration and is printed before any call.
Authentication is `gcloud auth application-default login` (no key files).
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from analyst.inference.llm import (
    THINKING_ORDER,
    ChatRequest,
    LlmError,
    billed_output_tokens,
    gcloud_token,
    http_transport,
    parse_json,
    vertex_base_url,
)

ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIG = ROOT / "configs" / "model.yaml"
MAX_CALLS = 6
SYSTEM = (
    "You write one DuckDB SQL query over the table given. Return one JSON object: "
    '{"sql": "...", "statement": "one line saying what the rows are"}.'
)
USER = (
    "Table obs_plfs_state_ur_usual_status(geo_name VARCHAR, period_label VARCHAR, "
    "period_start DATE, indicator_id VARCHAR, value DOUBLE, unit VARCHAR, is_total_row BOOLEAN). "
    "Plan: indicator ur_usual_ps_ss; every state, excluding total rows; period starting "
    "2019-07-01; rank by value, highest first; top 3."
)


def gcloud_value(key: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        ["gcloud", "config", "get-value", key],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.stdout.strip()


def plan_levels(requested: list[str] | None, accepted: list[str] | None) -> list[str]:
    """Default: the lowest accepted level and medium."""
    if requested:
        return requested
    lowest = next((x for x in THINKING_ORDER if not accepted or x in accepted), "low")
    return [lowest] if lowest == "medium" else [lowest, "medium"]


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--tier", default=None, help="tier name in model.yaml (default tier)")
    parser.add_argument("--model", help="a Gemini model id not in the tiers (google/ is added)")
    parser.add_argument("--price-in", type=float, help="USD per 1M input tokens (with --model)")
    parser.add_argument("--price-out", type=float, help="USD per 1M output tokens (with --model)")
    parser.add_argument("--levels", nargs="+", choices=[*THINKING_ORDER, "none"])
    parser.add_argument("--yes", action="store_true", help="send the calls (spends credit)")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    config = yaml.safe_load(MODEL_CONFIG.read_text(encoding="utf-8"))["hosted_llm"]
    tier = args.tier or config["default_tier"]
    model = args.model or config["tiers"][tier]
    if args.model:
        tier = "ad hoc"
    location = config["location"]
    cap = int(config.get("max_output_tokens", {}).get("sql", 512))
    prices = dict(config.get("price_per_mtok", {}).get(tier) or {})
    if args.model:
        prices = {"input": args.price_in, "output": args.price_out}
    accepted = (config.get("thinking", {}).get("supported_levels") or {}).get(model)
    levels = plan_levels(args.levels, accepted)
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or gcloud_value("project")
    account = gcloud_value("account")

    if len(levels) > MAX_CALLS:
        print(f"refused: {len(levels)} calls requested, at most {MAX_CALLS}")
        return 2
    worst = None
    if prices.get("input") is not None and prices.get("output") is not None:
        worst = len(levels) * (400 * prices["input"] + cap * prices["output"]) / 1e6
    print(f"account  {account}\nproject  {project}\nlocation {location}")
    print(f"model    google/{model} (tier {tier})\nlevels   {levels}\noutput cap {cap} tokens")
    print(
        f"calls    {len(levels)}; worst-case cost {'unknown' if worst is None else f'${worst:.5f}'}"
    )
    if not args.yes:
        print("plan only: nothing sent (add --yes to send)")
        return 0
    if not project or not location:
        print("refused: no project or location")
        return 2

    send = http_transport(vertex_base_url(project, location), gcloud_token)
    rows = []
    for level in levels:
        effort = None if level == "none" else level
        request = ChatRequest(SYSTEM, USER, f"google/{model}", 0.0, cap, effort)
        row: dict[str, object] = {"model": request.model, "level": level}
        try:
            reply = send(request)
        except LlmError as error:
            row["error"] = str(error)[:300]
            rows.append(row)
            print(json.dumps(row))
            continue
        try:
            parse_json(reply.content)
            valid = True
        except LlmError:
            valid = False
        cost = None
        if worst is not None:
            billed = billed_output_tokens(reply)
            cost = (reply.tokens_in * prices["input"] + billed * prices["output"]) / 1e6
        row |= {
            "served_model": reply.served_model,
            "latency_ms": reply.latency_ms,
            "tokens_in": reply.tokens_in,
            "tokens_out": reply.tokens_out,
            "reasoning_tokens": reply.reasoning_tokens,
            "finish_reason": reply.finish_reason,
            "valid_json": valid,
            "visible_chars": len(reply.content),
            "cost_usd_est": cost,
        }
        rows.append(row)
        print(json.dumps(row))
    total = sum(float(r["cost_usd_est"] or 0) for r in rows if "cost_usd_est" in r)  # type: ignore[arg-type]
    print(f"total estimated cost ${total:.6f}")
    if args.out:
        record = {
            "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "location": location,
            "tier": tier,
            "output_cap": cap,
            "calls": rows,
            "total_cost_usd_est": total,
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return 1 if any("error" in r for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
