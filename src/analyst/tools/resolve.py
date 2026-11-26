"""Resolve an interpretation plan against explicit catalogue/reference records."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from analyst.contracts.common import Assumption, IndicatorRef, Place
from analyst.contracts.intent import QueryIntent
from analyst.contracts.plan import InterpretationPlan, UnresolvedSlot
from analyst.tools.codelists import codelist
from analyst.tools.periods import (
    _year_type,
    latest_complete_period,
    resolve_period,
    season_codes,
)
from analyst.tools.places import (
    FILTER_LEVELS,
    alias_candidates,
    compact,
    is_national,
    map_state_to_subdivisions,
    normalise,
    resolve_filter_place,
    resolve_place,
    split_qualifier,
)

# The total of an area or sector breakdown, used when the question names none (design D1-D8:
# defaults are applied by code and stated in the answer).
# Values that mean "all of this breakdown" in a category column, in order of preference. Any
# category column whose codelist holds one gets it as the default (not only area and sector).
TOTAL_VALUES = ("total", "all", "rural+urban", "rural + urban", "combined", "persons", "both")


def _known_values(dataset_id: str, categories: dict[str, list[str]]) -> dict[str, list[str]]:
    """Keep only category values that exist in their column and are not copied from another
    column; a column left with none is dropped. Matching ignores case and spacing. Smoke run,
    19 Nov: the intent copied the commodity into the variety column ("variety: Potato"), which
    kept only the rows of the generic variety of that name."""
    kept: dict[str, list[str]] = {}
    # A value repeated from another column ("commodity_name: Potato", "variety: Potato") is a
    # copy: as a variety it would keep only the rows of the generic variety named "Potato".
    first: dict[str, str] = {}
    for column, values in categories.items():
        for value in values:
            first.setdefault(value.strip().casefold(), column)
    categories = {
        column: [v for v in values if first[v.strip().casefold()] == column]
        for column, values in categories.items()
    }
    for column, values in categories.items():
        known = {str(v).strip().casefold(): str(v) for v in codelist(dataset_id, column)}
        if not known:  # no codelist to check against: keep as given
            kept[column] = values
            continue
        found = [known[v.strip().casefold()] for v in values if v.strip().casefold() in known]
        if found:
            kept[column] = found
    return kept


def total_value(dataset_id: str, column: str) -> str | None:
    """The codelist value of `column` that stands for the total, if there is exactly one kind."""
    values = {str(v).strip().casefold(): str(v) for v in codelist(dataset_id, column)}
    return next((values[t] for t in TOTAL_VALUES if t in values), None)


def _state_qualifiers(
    mentions: Sequence[str],
    dataset_id: str,
    levels: Sequence[str],
    refs: Mapping[str, Any],
    db: Any,
) -> dict[str, str]:
    """Mentions that are the State of another mention's place: {place mention: State}.

    "Aurangabad" and "Maharashtra" in one question name the Aurangabad of Maharashtra when the
    table holds Aurangabad in several States; the State mention is then a qualifier, not a
    second place (M5 fix A3; `configs/reference/duplicate_districts.csv` lists such names).
    """
    qualified: dict[str, str] = {}
    for mention in mentions:
        for level in levels:
            if resolve_place(mention, dataset_id, level, refs, db).status != "unresolved":
                continue
            for other in mentions:
                if other == mention or other in qualified.values():
                    continue
                found = resolve_place(mention, dataset_id, level, refs, db, state=other)
                if found.place is not None:
                    qualified[mention] = other
                    break
            if mention in qualified:
                break
    return qualified


def _subdivisions_of(
    mention: str, dataset_id: str, refs: Mapping[str, Any], db: Any
) -> tuple[list[Place], Assumption | None]:
    """A State named on the IMD sub-division table, read as the sub-divisions that cover it
    (M5 fix A1; `configs/reference/imd_subdivisions.csv`, column `states`)."""
    if refs.get("imd_subdivisions") is None:
        return [], None
    names: list[str] = []
    state = mention
    for asked in [mention, *alias_candidates(mention, refs)]:
        try:
            names = map_state_to_subdivisions(asked, refs)
        except ValueError:  # the reference holds no State column
            return [], None
        if names:
            state = asked
            break
    places = [
        found.place
        for name in names
        if (found := resolve_place(name, dataset_id, "subdivision", refs, db)).place is not None
    ]
    if not places:
        return [], None
    places = [p.model_copy(update={"requested": mention, "match": "alias"}) for p in places]
    if len(places) > 1:
        listed = ", ".join(p.name for p in places)
        text = (
            f"IMD publishes no figure for {state} as a whole: {state} is covered by "
            f"{len(places)} sub-divisions ({listed}), one row each."
        )
    else:
        text = f"{mention} is read as the IMD sub-division '{places[0].name}'."
    shared = _shared_states(places, state, refs)
    if shared:
        text += f" {shared}"
    return places, Assumption(code="SUBDIVISION", text=text)


def _shared_states(places: Sequence[Place], state: str, refs: Mapping[str, Any]) -> str:
    """The note for sub-divisions that also cover other States ("Haryana Delhi & Chandigarh")."""
    ref = refs["imd_subdivisions"]
    frame = ref if isinstance(ref, pd.DataFrame) else pd.read_csv(ref, dtype=str)
    covers = {
        str(row["subdivision"]): [p.strip() for p in str(row["states"]).split(";") if p.strip()]
        for _, row in frame.iterrows()
        if "states" in frame.columns
    }
    notes = []
    for place in places:
        others = [s for s in covers.get(place.name, []) if normalise(s) != normalise(state)]
        if others:
            notes.append(
                f"'{place.name}' also covers {' and '.join(others)}; its figure is for the "
                "whole sub-division."
            )
    return " ".join(notes)


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
    assumptions: list[Assumption] = []
    all_levels = (
        [str(intent.all_places_level)]
        if intent.all_places_level
        else [str(level) for level in dataset.get("geo_levels", [])]
    )
    qualifiers = _state_qualifiers(intent.place_mentions, dataset_id, all_levels, refs, db)
    for mention, state in qualifiers.items():
        assumptions.append(
            Assumption(code="PLACE_STATE", text=f"{mention} is read as {mention} in {state}.")
        )
    for mention in intent.place_mentions:
        if mention in qualifiers.values():  # the State of another mention, not a place
            continue
        if is_national(mention) and "national" in dataset.get("geo_levels", []):
            national = resolve_place("India", dataset_id, "national", refs, db)
            if national.place is not None:
                places.append(national.place.model_copy(update={"requested": mention}))
                continue
        levels = (
            [str(intent.all_places_level)]
            if intent.all_places_level
            else [str(level) for level in dataset.get("geo_levels", [])]
        )
        resolutions = [
            resolve_place(mention, dataset_id, level, refs, db, state=qualifiers.get(mention))
            for level in levels
        ]
        matches = [resolution.place for resolution in resolutions if resolution.place is not None]
        if not matches and "subdivision" in levels:
            covering, note = _subdivisions_of(mention, dataset_id, refs, db)
            if covering:
                places.extend(covering)
                if note is not None:
                    assumptions.append(note)
                continue
        filters = [f for level in levels for f in FILTER_LEVELS.get(level, ()) if f not in levels]
        # A State or district named on a finer table filters its rows, also when the question
        # names the finer level ("Uttar Pradesh markets": dev run 3, e2e-042).
        if not matches and not any(resolution.options for resolution in resolutions):
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
        place = matches[0]
        asked = split_qualifier(mention)[0]
        if (
            place.match == "alias"
            and compact(place.name) != compact(asked)
            and place.level
            in {
                "subdivision",
                "market",
                "district",
            }
        ):
            # "Odisha" is the sub-division "Orissa"; "Azadpur" is the market "APMC Azadpur".
            assumptions.append(
                Assumption(
                    code="ALIAS", text=f"{asked} is read as '{place.name}', the name in the table."
                )
            )
        if " including " in place.name.casefold() and " including " not in mention.casefold():
            assumptions.append(
                Assumption(
                    code="D6", text=f"{mention} is read as '{place.name}', the name in the table."
                )
            )
        places.append(place)
    periods = []
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
    seasons = None
    if intent.period_mentions and "season" in dataset.get("period_types", []):
        if not re.fullmatch(r"obs_[a-z][a-z0-9_]*", obs_table):
            raise ValueError("invalid observation table name")
        seasons = season_codes(
            db.execute(
                f"SELECT DISTINCT period_label, period_start, period_end FROM {obs_table} "  # noqa: S608 - validated identifier
                "WHERE period_type = 'season' ORDER BY period_start LIMIT 24"
            ).fetchall()
        )
    for mention in intent.period_mentions:
        resolution = resolve_period(mention, dataset_id, catalogue, round_labels, seasons or None)
        if resolution.status != "resolved" or resolution.window is None:
            unresolved.append(
                UnresolvedSlot(slot="period", mention=mention, options=resolution.options)
            )
        else:
            periods.append(resolution.window)
            if resolution.assumption is not None:
                assumptions.append(resolution.assumption)
    single = intent.operation in {"lookup", "ranking", "comparison", "share", "aggregate"}
    if not intent.period_mentions and single and not intent.derivations:
        # D1: no period named -> the latest period the table publishes, stated in the answer.
        types = [str(t) for t in dataset.get("period_types", [])]
        kind = _year_type(set(types), dataset.get("period_start_month")) or (
            types[0] if types else None
        )
        if kind is not None:
            try:
                latest = latest_complete_period(dataset_id, kind, db)
            except LookupError:
                latest = None
            if latest is not None:
                periods.append(latest)
                assumptions.append(
                    Assumption(code="D1", text=f"No period named: the latest, {latest.label}.")
                )
    categories = _known_values(dataset_id, dict(intent.categories))
    for column in dataset.get("categories") or {}:
        total = total_value(dataset_id, column) if column not in categories else None
        if total is not None:
            categories[column] = [total]
            assumptions.append(
                Assumption(code="TOTAL", text=f"{column} = {total}: no {column} was named.")
            )
    return InterpretationPlan(
        dataset_id=dataset_id,
        obs_table=obs_table,
        dataset_version=str(dataset_version),
        indicators=resolved_indicators,
        places=places,
        all_places_level=intent.all_places_level,
        periods=periods,
        categories=categories,
        operation=intent.operation,
        order=intent.order,
        limit=intent.limit,
        derivations=intent.derivations,
        # The national row is flagged as the table's total row; asking for it keeps total rows.
        exclude_total_rows=not any(place.level == "national" for place in places),
        assumptions=list({item.code + item.text: item for item in assumptions}.values()),
        unresolved=unresolved,
    )
