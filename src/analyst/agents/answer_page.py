"""One HTML page per run for local demos: answer, chart, rows, SQL and assumptions.

The page is written from the run state only (no new figures). The chart is the run's
Vega-Lite specification, drawn in the browser by vega-embed from a pinned CDN version.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from analyst.agents.state import AnalystState

VEGA = "https://cdn.jsdelivr.net/npm/vega@5.30.0"
VEGA_LITE = "https://cdn.jsdelivr.net/npm/vega-lite@5.21.0"
VEGA_EMBED = "https://cdn.jsdelivr.net/npm/vega-embed@6.26.0"
MAX_TABLE_ROWS = 50

_STYLE = """
body{font:15px/1.5 system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;
color:#1f2328;background:#fff}h1{font-size:1.2rem}h2{font-size:1rem;margin-top:1.6rem}
.answer{background:#f6f8fa;border-left:4px solid #0969da;padding:.8rem 1rem}
.meta{color:#59636e;font-size:.85rem}table{border-collapse:collapse;font-size:.85rem}
td,th{border:1px solid #d1d9e0;padding:.25rem .5rem;text-align:left}
pre{background:#f6f8fa;padding:.8rem;overflow-x:auto;font-size:.8rem}
.value{font-size:2rem;font-weight:600}
"""


def _table(columns: list[str], rows: list[list[Any]]) -> str:
    """Render result rows as an HTML table, showing at most MAX_TABLE_ROWS rows."""
    head = "".join(f"<th>{html.escape(c)}</th>" for c in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row) + "</tr>"
        for row in rows[:MAX_TABLE_ROWS]
    )
    more = f"<p class='meta'>{len(rows) - MAX_TABLE_ROWS} more rows not shown.</p>"
    return f"<table><tr>{head}</tr>{body}</table>" + (more if len(rows) > MAX_TABLE_ROWS else "")


def answer_page(state: AnalystState) -> str:
    """The page for one run, as an HTML string."""
    parts = [
        f"<h1>{html.escape(state.question)}</h1>",
        f"<p class='meta'>Outcome: {html.escape(str(state.outcome))}"
        + (f" ({html.escape(str(state.outcome_cause))})" if state.outcome_cause else "")
        + f" · run {html.escape(state.run_id)}</p>",
        f"<div class='answer'>{html.escape(state.response_text or '')}</div>",
    ]
    chart = state.chart
    spec = chart.vega_lite if chart else None
    result = state.result
    if chart is not None and spec:
        payload = json.dumps(spec, default=str).replace("</", "<\\/")
        parts += [
            f"<h2>Chart ({html.escape(chart.chart_type)})</h2><div id='chart'></div>",
            f"<script>vegaEmbed('#chart', {payload}, {{actions: false}});</script>",
        ]
    elif chart is not None and chart.chart_type == "single_value" and result and result.rows:
        names = [c.name for c in result.columns]
        if "value" in names:
            value = result.rows[0][names.index("value")]
            parts.append(f"<h2>Value</h2><p class='value'>{html.escape(str(value))}</p>")
    if result is not None:
        parts += ["<h2>Rows returned</h2>", _table([c.name for c in result.columns], result.rows)]
        parts += ["<h2>SQL</h2>", f"<pre>{html.escape(result.sql)}</pre>"]
    if state.plan is not None and state.plan.assumptions:
        items = "".join(f"<li>{html.escape(a.text)}</li>" for a in state.plan.assumptions)
        parts += ["<h2>Assumptions</h2>", f"<ul>{items}</ul>"]
    scripts = "".join(f"<script src='{src}'></script>" for src in (VEGA, VEGA_LITE, VEGA_EMBED))
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Analyst answer</title><style>{_STYLE}</style>{scripts}</head><body>"
        + "".join(parts)
        + "</body></html>"
    )


def save_answer_page(state: AnalystState, directory: Path) -> Path:
    """Write the page to `<directory>/<run_id>.html` and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{state.run_id}.html"
    path.write_text(answer_page(state), encoding="utf-8")
    return path
