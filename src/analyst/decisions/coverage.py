"""`check_coverage` and `define_supported_scope_and_caveats` (design document Section 5).

Rules decide, in this order: dataset, indicators, geo level, period range and grain,
categories, derivation inputs (a per-capita value needs a population table). Every missing
part is listed. Some parts covered and some not gives `partial` with the supported plan; none
covered gives `not_covered` with up to three related tables as pointers; unresolved slots give
`ambiguous` (the graph asks a clarifying question). Jev for "does this measure match this
indicator" is a Should and is not used here (`decided_by="rules"`, `probability=None`).

`catalogue` is the published catalogue (`data/processed/catalogue.json`), as a mapping from
`dataset_id` to its entry.
"""

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, Literal

from analyst.contracts.coverage import CoverageResult, MissingPart
from analyst.contracts.plan import InterpretationPlan
from analyst.tools.places import FILTER_LEVELS

ROOT = Path(__file__).resolve().parents[3]
PUBLISHED = ROOT / "data" / "processed" / "catalogue.json"
POPULATION_HINT = "population"
MAX_POINTERS = 3

Catalogue = Mapping[str, Mapping[str, Any]]


def load_published(path: Path = PUBLISHED) -> dict[str, dict[str, Any]]:
    tables = json.loads(path.read_text(encoding="utf-8"))["tables"]
    return {t["dataset_id"]: t for t in tables}


def _date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _has_population(catalogue: Catalogue) -> bool:
    return any(
        POPULATION_HINT in indicator
        for t in catalogue.values()
        for indicator in t.get("indicator_units", {})
    )


def pointers_for(catalogue: Catalogue, dataset_id: str | None, domain: str | None) -> list[str]:
    """Up to three related tables for a decline: same domain first, never the plan's own."""
    ranked = sorted(
        (t for d, t in catalogue.items() if d != dataset_id),
        key=lambda t: (t.get("domain") != domain, t["dataset_id"]),
    )
    return [t["dataset_id"] for t in ranked if domain is None or t.get("domain") == domain][
        :MAX_POINTERS
    ]


def check_coverage(
    plan: InterpretationPlan,
    catalogue: Catalogue,
    evidence: Any = None,
    jev: Any = None,
    domain: str | None = None,
) -> CoverageResult:
    if plan.unresolved:
        return _result(
            "ambiguous",
            [
                MissingPart(kind="definition", detail=u.slot + ": " + u.mention)
                for u in plan.unresolved
            ],
            plan=None,
        )
    table = catalogue.get(plan.dataset_id)
    if table is None:
        absent = [MissingPart(kind="indicator", detail=f"no table {plan.dataset_id!r}")]
        return _result("not_covered", absent, pointers=pointers_for(catalogue, None, domain))
    missing: list[MissingPart] = []
    left_out: list[str] = []
    indicators = table.get("indicator_units", {})
    kept_indicators = [i for i in plan.indicators if i.indicator_id in indicators]
    for i in plan.indicators:
        if i.indicator_id not in indicators:
            missing.append(MissingPart(kind="indicator", detail=i.indicator_id))
            left_out.append(f"indicator {i.indicator_id}")
    levels = {p.level for p in plan.places} | (
        {plan.all_places_level} if plan.all_places_level else set()
    )
    table_levels = set(table.get("geo_levels", []))
    # A State (or district) named on a finer table is a filter on its rows, not a missing level.
    filters = {f for level in table_levels for f in FILTER_LEVELS.get(level, ())}
    place_levels = {p.level for p in plan.places}
    absent_levels = sorted(
        (place_levels - table_levels - filters)
        | ({plan.all_places_level} - table_levels if plan.all_places_level else set())
    )
    for level in absent_levels:
        missing.append(MissingPart(kind="geo_level", detail=f"{level} not in {plan.dataset_id}"))
    kept_places = [p for p in plan.places if p.level not in absent_levels]
    left_out += [f"place {p.name}" for p in plan.places if p.level in absent_levels]
    start, end = _date(table["coverage_start"]), _date(table["coverage_end"])
    period_types = set(table.get("period_types", []))
    kept_periods = []
    for period in plan.periods:
        if period.type not in period_types:
            missing.append(
                MissingPart(kind="period", detail=f"{period.label}: no {period.type} grain")
            )
            left_out.append(f"period {period.label}")
        elif period.start < start or period.end > end:
            missing.append(
                MissingPart(kind="period", detail=f"{period.label} outside {start} to {end}")
            )
            left_out.append(f"period {period.label}")
        else:
            kept_periods.append(period)
    codelists = table.get("categories", {})
    for column, values in plan.categories.items():
        known = codelists.get(column)
        bad = values if known is None else [v for v in values if v not in known]
        if bad:
            missing.append(MissingPart(kind="category", detail=f"{column}: {bad}"))
    for derivation in plan.derivations:
        if derivation.op == "per_capita" and not _has_population(catalogue):
            missing.append(
                MissingPart(kind="population", detail="per-capita value needs a population table")
            )
    if not missing:
        return _result("covered", [], plan=None)
    blocking = {m.kind for m in missing} & {"category", "population"}
    nothing_left = (
        (plan.indicators and not kept_indicators)
        or (plan.periods and not kept_periods)
        or (levels and set(absent_levels) == levels)
    )
    if blocking or nothing_left:
        return _result(
            "not_covered",
            missing,
            pointers=pointers_for(catalogue, plan.dataset_id, table.get("domain")),
        )
    supported = plan.model_copy(
        update={"indicators": kept_indicators, "periods": kept_periods, "places": kept_places}
    )
    return _result("partial", missing, plan=supported, left_out=left_out)


def _result(
    status: Literal["covered", "partial", "ambiguous", "not_covered"],
    missing: list[MissingPart],
    plan: InterpretationPlan | None = None,
    left_out: list[str] | None = None,
    pointers: list[str] | None = None,
) -> CoverageResult:
    return CoverageResult(
        status=status,
        probability=None,
        decided_by="rules",
        missing=missing,
        supported_plan=plan,
        left_out=left_out or [],
        pointers=pointers or [],
    )


def restrict(plan: InterpretationPlan, coverage: CoverageResult) -> CoverageResult:
    """`define_supported_scope_and_caveats`: confirm the supported part of a partial answer.
    A plan is answered from one table, so its parts are comparable; a supported plan with no
    indicator or no period left is not answerable and becomes `not_covered`."""
    if coverage.status != "partial":
        return coverage
    supported = coverage.supported_plan
    if supported is None or not supported.indicators or (plan.periods and not supported.periods):
        return coverage.model_copy(update={"status": "not_covered", "supported_plan": None})
    return coverage
