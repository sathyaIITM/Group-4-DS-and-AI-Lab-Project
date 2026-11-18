"""Resolve an interpretation plan against explicit catalogue/reference records."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from analyst.contracts.common import Assumption, IndicatorRef, Place
from analyst.contracts.intent import QueryIntent
from analyst.contracts.plan import InterpretationPlan, UnresolvedSlot
from analyst.tools.periods import resolve_period
from analyst.tools.places import FILTER_LEVELS, resolve_filter_place, resolve_place


def resolve_plan(
    intent: QueryIntent,
    *,
    dataset: Mapping[str, Any],
    indicators: Sequence[Mapping[str, Any]],
    db: Any,
    refs: Mapping[str, Any],
    catalogue: Any,
) -> InterpretationPlan:
    """Build a plan from catalogued values; ambiguous mentions remain unresolved."""
    if not dataset.get("dataset_id"):
        raise ValueError("dataset metadata must include dataset_id")
    dataset_id = str(dataset["dataset_id"])
    obs_table = str(dataset.get("obs_table") or f"obs_{dataset_id}")
    dataset_version = dataset.get("dataset_version")
    if dataset_version is None:
        if not re.fullmatch(r"obs_[a-z][a-z0-9_]*", obs_table):
            raise ValueError("invalid observation table name")
        version_row = db.execute(
            f"SELECT dataset_version FROM {obs_table} ORDER BY dataset_version DESC LIMIT 1"  # noqa: S608 - validated identifier
        ).fetchone()
        dataset_version = version_row[0] if version_row else "unknown"
    indicator_by_id = {str(row["indicator_id"]): row for row in indicators}
    resolved_indicators: list[IndicatorRef] = []
    unresolved: list[UnresolvedSlot] = []
    for requested in intent.indicator_ids:
        row = indicator_by_id.get(requested)
        if row is None:
            label_matches = [
                r for r in indicators if str(r.get("label", "")).casefold() == requested.casefold()
            ]
            if len(label_matches) != 1:
                unresolved.append(
                    UnresolvedSlot(
                        slot="indicator",
                        mention=requested,
                        options=[
                            str(r.get("label", r.get("indicator_id", "")))
                            for r in label_matches[:6]
                        ],
                    )
                )
                continue
            row = label_matches[0]
        resolved_indicators.append(
            IndicatorRef(
                indicator_id=str(row["indicator_id"]),
                label=str(row["label"]),
                unit=str(row["unit"]),
            )
        )
    places: list[Place] = []
    for mention in intent.place_mentions:
        levels = (
            [str(intent.all_places_level)]
            if intent.all_places_level
            else [str(level) for level in dataset.get("geo_levels", [])]
        )
        resolutions = [resolve_place(mention, dataset_id, level, refs, db) for level in levels]
        matches = [resolution.place for resolution in resolutions if resolution.place is not None]
        filters = [f for level in levels for f in FILTER_LEVELS.get(level, ()) if f not in levels]
        if (
            not matches
            and not intent.all_places_level
            and not any(resolution.options for resolution in resolutions)
        ):
            for level in dict.fromkeys(filters):
                found = resolve_filter_place(mention, dataset_id, level, refs, db)
                if found.place is not None:
                    matches.append(found.place)
        if len(matches) != 1:
            options = [f"{place.name} ({place.level})" for place in matches]
            options.extend(option for resolution in resolutions for option in resolution.options)
            unresolved.append(
                UnresolvedSlot(
                    slot="place", mention=mention, options=list(dict.fromkeys(options))[:6]
                )
            )
            continue
        places.append(matches[0])
    periods = []
    assumptions: list[Assumption] = []
    round_labels: list[str] | None = None
    if intent.period_mentions and set(dataset.get("period_types", [])) == {"survey_round"}:
        if not re.fullmatch(r"obs_[a-z][a-z0-9_]*", obs_table):
            raise ValueError("invalid observation table name")
        round_labels = [
            str(row[0])
            for row in db.execute(
                f"SELECT DISTINCT period_label FROM {obs_table} "  # noqa: S608 - validated identifier
                "WHERE period_label IS NOT NULL ORDER BY period_label"
            ).fetchall()
        ]
    for mention in intent.period_mentions:
        resolution = resolve_period(mention, dataset_id, catalogue, round_labels)
        if resolution.status != "resolved" or resolution.window is None:
            unresolved.append(
                UnresolvedSlot(slot="period", mention=mention, options=resolution.options)
            )
        else:
            periods.append(resolution.window)
            if resolution.assumption is not None:
                assumptions.append(resolution.assumption)
    return InterpretationPlan(
        dataset_id=dataset_id,
        obs_table=obs_table,
        dataset_version=str(dataset_version),
        indicators=resolved_indicators,
        places=places,
        all_places_level=intent.all_places_level,
        periods=periods,
        categories=intent.categories,
        operation=intent.operation,
        order=intent.order,
        limit=intent.limit,
        derivations=intent.derivations,
        exclude_total_rows=True,
        assumptions=list({item.code + item.text: item for item in assumptions}.values()),
        unresolved=unresolved,
    )
