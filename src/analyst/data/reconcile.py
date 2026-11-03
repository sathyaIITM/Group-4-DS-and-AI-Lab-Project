"""Comparison of a new release of a dataset with the live one.

Public data changes without notice: a publisher moves its year window, renames a period,
revises earlier values, drops old years or adds a breakdown. The checks on a single run
cannot see any of that, because each run is internally consistent. This module compares
the new observation table with the one currently published for the same dataset, on the
observation key (place, period, indicator, categories), and reports what changed.

Structural changes that would break stored queries or silently move earlier results are
blocking items. A person who has looked at them can accept them with a stated reason; the
reason is kept in the lineage record. Comparing different datasets is out of scope here.
"""

from typing import Any

import numpy as np
import pandas as pd

from analyst.data.config import SourceConfig
from analyst.data.contract import OBS_HEAD, OBS_TAIL, ReviewItem, Severity
from analyst.data.validate import category_columns, key_columns

# Blocking kinds a person may accept with a reason. Anything else stays blocking.
ACCEPTABLE_KINDS = frozenset(
    {
        "period_redated",
        "period_relabelled",
        "values_revised",
        "rows_removed",
        "indicators_removed",
        "unit_changed",
        "period_type_changed",
        "category_columns_changed",
    }
)
EXAMPLES = 3


def _extras(frame: pd.DataFrame) -> list[str]:
    return [c for c in frame.columns if c not in OBS_HEAD and c not in OBS_TAIL]


def _differs(left: pd.Series, right: pd.Series) -> pd.Series:
    return (left != right) & ~(left.isna() & right.isna())


def _names(values: set[Any], limit: int = 5) -> list[str]:
    return sorted(str(v) for v in values)[:limit]


def _item(
    config: SourceConfig,
    severity: Severity,
    kind: str,
    detail: str,
    count: int,
    suggestion: str = "",
) -> ReviewItem:
    return ReviewItem(
        dataset_id=config.dataset_id,
        severity=severity,
        kind=kind,
        detail=detail,
        count=count,
        suggestion=suggestion,
    )


def compare_releases(
    config: SourceConfig, previous: pd.DataFrame, current: pd.DataFrame
) -> tuple[list[ReviewItem], dict[str, Any]]:
    """Review items and a summary of how ``current`` differs from ``previous``."""
    items: list[ReviewItem] = []
    limits = config.reconcile
    summary: dict[str, Any] = {"previous_rows": len(previous), "current_rows": len(current)}

    # --- Shape of the table -----------------------------------------------------------
    if set(_extras(previous)) != set(_extras(current)):
        gone = set(_extras(previous)) - set(_extras(current))
        new = set(_extras(current)) - set(_extras(previous))
        items.append(
            _item(
                config,
                "block",
                "category_columns_changed",
                "category or attribute columns changed: "
                f"removed {_names(gone)}, added {_names(new)}",
                len(gone | new),
                "update [columns]; queries that filter on a removed column will fail",
            )
        )
    old_indicators = set(previous["indicator_id"])
    new_indicators = set(current["indicator_id"])
    if old_indicators - new_indicators:
        gone = old_indicators - new_indicators
        items.append(
            _item(
                config,
                "block",
                "indicators_removed",
                f"{len(gone)} indicators are no longer published, e.g. {_names(gone)}",
                len(gone),
                "confirm the removal; stored queries and routing examples may name them",
            )
        )
    if new_indicators - old_indicators:
        added = new_indicators - old_indicators
        items.append(
            _item(
                config,
                "info",
                "indicators_added",
                f"{len(added)} new indicators, e.g. {_names(added)}",
                len(added),
            )
        )
    old_units = previous.drop_duplicates("indicator_id").set_index("indicator_id")["unit"]
    new_units = current.drop_duplicates("indicator_id").set_index("indicator_id")["unit"]
    shared = old_units.index.intersection(new_units.index)
    changed_units = [i for i in shared if old_units[i] != new_units[i]]
    if changed_units:
        examples = [f"{i}: {old_units[i]} -> {new_units[i]}" for i in changed_units[:EXAMPLES]]
        items.append(
            _item(
                config,
                "block",
                "unit_changed",
                f"{len(changed_units)} indicators changed unit, e.g. {examples}",
                len(changed_units),
                "a changed unit makes old and new values incomparable; check the source",
            )
        )
    old_types = set(previous["period_type"])
    new_types = set(current["period_type"])
    if old_types - new_types:
        items.append(
            _item(
                config,
                "block",
                "period_type_changed",
                f"period types {_names(old_types - new_types)} are no longer published "
                f"(now {_names(new_types)})",
                len(old_types - new_types),
                "a different period type changes what 'a year' means; confirm and accept",
            )
        )
    old_places = set(previous["geo_code"])
    new_places = set(current["geo_code"])
    if old_places - new_places:
        gone = old_places - new_places
        items.append(
            _item(
                config,
                "warn",
                "places_removed",
                f"{len(gone)} places are no longer published, e.g. {_names(gone)}",
                len(gone),
                "a merged or renamed place needs an alias or a lineage entry",
            )
        )
    if new_places - old_places:
        added = new_places - old_places
        items.append(
            _item(
                config,
                "info",
                "places_added",
                f"{len(added)} new places, e.g. {_names(added)}",
                len(added),
                "check the place reference list if these are new districts or States",
            )
        )
    for column in category_columns(config):
        if column not in previous.columns or column not in current.columns:
            continue
        old_values = set(previous[column].dropna())
        new_values = set(current[column].dropna())
        if new_values - old_values:
            added = new_values - old_values
            items.append(
                _item(
                    config,
                    "info",
                    "category_values_added",
                    f"{column}: {len(added)} new values, e.g. {_names(added)}",
                    len(added),
                )
            )
        if old_values - new_values:
            gone = old_values - new_values
            items.append(
                _item(
                    config,
                    "warn",
                    "category_values_removed",
                    f"{column}: {len(gone)} values no longer published, e.g. {_names(gone)}",
                    len(gone),
                )
            )

    # --- Observations on the shared key ----------------------------------------------
    key = [c for c in key_columns(config) if c in previous.columns and c in current.columns]
    columns = [*key, "value", "period_start", "period_end"]
    earlier = previous.drop_duplicates(key)[columns]
    later = current.drop_duplicates(key)[columns]
    merged = earlier.merge(later, on=key, how="outer", suffixes=("_old", "_new"), indicator=True)
    both = merged[merged["_merge"] == "both"]
    removed = merged[merged["_merge"] == "left_only"]
    appeared = merged[merged["_merge"] == "right_only"]

    redated = both[
        _differs(both["period_start_old"], both["period_start_new"])
        | _differs(both["period_end_old"], both["period_end_new"])
    ]
    if len(redated):
        examples = [
            f"{r.period_label}: {r.period_start_old:%Y-%m-%d}..{r.period_end_old:%Y-%m-%d} -> "
            f"{r.period_start_new:%Y-%m-%d}..{r.period_end_new:%Y-%m-%d}"
            for r in redated.drop_duplicates("period_label").head(EXAMPLES).itertuples()
        ]
        items.append(
            _item(
                config,
                "block",
                "period_redated",
                f"{len(redated)} earlier values now sit in different dates under the same "
                f"label, e.g. {examples}",
                len(redated),
                "a year window changed for periods already published: keep earlier years on "
                "their old window with period.conventions, or accept if the source corrected it",
            )
        )

    stable = both.drop(redated.index)
    pairs = stable[stable["value_old"].notna() & stable["value_new"].notna()]
    revised_mask = ~np.isclose(
        pairs["value_old"].to_numpy(dtype=float),
        pairs["value_new"].to_numpy(dtype=float),
        rtol=limits.value_rtol,
        atol=1e-9,
    )
    revised = pairs[revised_mask]
    share = len(revised) / len(pairs) if len(pairs) else 0.0
    if len(revised):
        change = (revised["value_new"] - revised["value_old"]).abs()
        severity: Severity = "block" if share > limits.max_revised_share else "warn"
        items.append(
            _item(
                config,
                severity,
                "values_revised",
                f"{len(revised)} of {len(pairs)} shared values changed ({share:.1%}); "
                f"largest change {change.max():g}",
                len(revised),
                "revisions are normal in small numbers; a large share points to a changed "
                "definition, window or unit: compare against the publisher's note",
            )
        )
    availability = stable[stable["value_old"].isna() != stable["value_new"].isna()]
    if len(availability):
        items.append(
            _item(
                config,
                "warn",
                "value_availability_changed",
                f"{len(availability)} values became missing or were filled in",
                len(availability),
            )
        )

    # --- Rows that appeared or vanished -----------------------------------------------
    place_keys = [c for c in key if c != "period_label"]
    by_dates = [*place_keys, "period_start", "period_end"]
    relabelled = 0
    if len(removed) and len(appeared):
        departed = removed[
            [*place_keys, "period_label", "period_start_old", "period_end_old"]
        ].rename(columns={"period_start_old": "period_start", "period_end_old": "period_end"})
        arrived = appeared[
            [*place_keys, "period_label", "period_start_new", "period_end_new"]
        ].rename(columns={"period_start_new": "period_start", "period_end_new": "period_end"})
        match = departed.merge(arrived, on=by_dates, suffixes=("_old", "_new"))
        match = match[match["period_label_old"] != match["period_label_new"]]
        relabelled = len(match)
        if relabelled:
            examples = list(
                dict.fromkeys(
                    f"{a} -> {b}"
                    for a, b in zip(
                        match["period_label_old"], match["period_label_new"], strict=True
                    )
                )
            )[:EXAMPLES]
            items.append(
                _item(
                    config,
                    "block",
                    "period_relabelled",
                    f"{relabelled} values keep their dates but changed period label, "
                    f"e.g. {examples}",
                    relabelled,
                    "queries that filter on the old label break; map the labels or accept",
                )
            )
    removed_net = max(len(removed) - relabelled, 0)
    if removed_net:
        removed_share = removed_net / max(len(earlier), 1)
        removed_severity: Severity = "block" if removed_share > limits.max_removed_share else "warn"
        labels = sorted(set(removed["period_label"].astype(str)))
        items.append(
            _item(
                config,
                removed_severity,
                "rows_removed",
                f"{removed_net} earlier observations are gone ({removed_share:.1%}); "
                f"periods affected include {labels[:5]}",
                removed_net,
                "confirm the publisher dropped them on purpose (for example a rolling window)",
            )
        )
    added_net = max(len(appeared) - relabelled, 0)
    if added_net:
        labels = sorted(set(appeared["period_label"].astype(str)))
        items.append(
            _item(
                config,
                "info",
                "rows_added",
                f"{added_net} new observations; periods include {labels[-5:]}",
                added_net,
            )
        )

    summary |= {
        "shared": len(both),
        "added": added_net,
        "removed": removed_net,
        "redated": len(redated),
        "relabelled": relabelled,
        "revised": len(revised),
        "revised_share": round(share, 6),
    }
    return items, summary


def accept_changes(
    items: list[ReviewItem], reason: str
) -> tuple[list[ReviewItem], list[dict[str, Any]]]:
    """Turn acceptable blocking items into info items that carry the stated reason."""
    kept: list[ReviewItem] = []
    accepted: list[dict[str, Any]] = []
    for item in items:
        if item.severity == "block" and item.kind in ACCEPTABLE_KINDS:
            kept.append(
                item.model_copy(
                    update={"severity": "info", "detail": f"accepted ({reason}): {item.detail}"}
                )
            )
            accepted.append({"kind": item.kind, "count": item.count, "reason": reason})
        else:
            kept.append(item)
    return kept, accepted
