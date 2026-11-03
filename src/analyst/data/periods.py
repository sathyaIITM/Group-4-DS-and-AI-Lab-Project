"""Checks on the periods of one observation table.

A year that begins in a different month, a window that is re-published, or a label that
no longer matches its dates leaves a trace in the periods: two periods of one series that
overlap, a hole between them, or a year later than anyone confirmed. These checks look
only at the periods that were built, so they apply to every table in the same way.
"""

import pandas as pd

from analyst.data.config import SourceConfig
from analyst.data.contract import ReviewItem
from analyst.data.validate import category_columns

# Period types whose consecutive periods are expected to follow each other without a hole.
ADJACENT_TYPES = frozenset({"calendar_year", "survey_year", "quarter"})
# Period types that recur at the same place in every year (June, the monsoon season). A table
# may hold only some of them, so the test is that a slot present in two years is present in
# all the years between.
RECURRING_TYPES = frozenset({"month", "season"})
# Period types that carry a published start year at the head of their label.
YEARLY_LABEL_TYPES = frozenset({"calendar_year", "survey_year", "quarter"})
EXAMPLES = 3


def _series_keys(config: SourceConfig) -> list[str]:
    return ["geo_code", "period_type", "indicator_id", *category_columns(config)]


def _adjacent_holes(frame: pd.DataFrame, keys: list[str], types: frozenset[str]) -> pd.DataFrame:
    """Rows whose period starts later than the day after the previous period ended."""
    grouped = frame.groupby(keys, sort=False, dropna=False)
    previous_end = grouped["period_end"].shift()
    previous_label = grouped["period_label"].shift()
    gap = (frame["period_start"] - previous_end).dt.days - 1
    hit = frame["period_type"].isin(types) & previous_end.notna() & (gap > 0)
    found = frame[hit].assign(
        previous_label=previous_label[hit], hole_year=previous_end[hit].dt.year
    )
    return found


def _recurring_holes(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Rows of a recurring slot that skip at least one year since the slot last appeared."""
    start = frame["period_start"]
    rows = frame[
        frame["period_type"].isin(RECURRING_TYPES) & ~((start.dt.month == 2) & (start.dt.day == 29))
    ]
    slot = [rows["period_start"].dt.month, rows["period_start"].dt.day, rows["period_end"].dt.month]
    rows = rows.assign(_slot=list(zip(*slot, strict=True)))
    rows = rows.sort_values([*keys, "_slot", "period_start"], kind="stable")
    grouped = rows.groupby([*keys, "_slot"], sort=False, dropna=False)
    previous_start = grouped["period_start"].shift()
    previous_label = grouped["period_label"].shift()
    skipped = rows["period_start"].dt.year - previous_start.dt.year
    hit = previous_start.notna() & (skipped > 1)
    found: pd.DataFrame = (
        rows[hit]
        .assign(previous_label=previous_label[hit], hole_year=previous_start[hit].dt.year)
        .drop(columns="_slot")
    )
    return found


def check_periods(config: SourceConfig, obs: pd.DataFrame) -> list[ReviewItem]:
    """Overlapping periods block; periods missing between two that are present warn."""
    if obs.empty:
        return []
    keys = _series_keys(config)
    frame = obs.loc[
        obs["period_start"].notna(), [*keys, "period_label", "period_start", "period_end"]
    ]
    frame = frame.drop_duplicates([*keys, "period_start", "period_end"])
    frame = frame.sort_values([*keys, "period_start", "period_end"], kind="stable")
    grouped = frame.groupby(keys, sort=False, dropna=False)
    frame = frame.assign(
        previous_end=grouped["period_end"].shift(),
        previous_label=grouped["period_label"].shift(),
    )
    overlap = frame["previous_end"].notna() & (frame["period_start"] <= frame["previous_end"])

    items: list[ReviewItem] = []
    if overlap.any():
        pairs = _examples(frame[overlap])
        series = frame.loc[overlap, keys].drop_duplicates().shape[0]
        items.append(
            ReviewItem(
                dataset_id=config.dataset_id,
                severity="block",
                kind="period_overlap",
                detail=(
                    f"{int(overlap.sum())} periods overlap the period before them, in {series} "
                    f"series of one period type, e.g. {pairs}"
                ),
                count=int(overlap.sum()),
                suggestion=(
                    "two year windows may be mixed in one table: declare the change in "
                    "period.conventions and state a transition year in period.exceptions, "
                    "or correct the labels at the source"
                ),
            )
        )

    expect = config.period.expect_contiguous
    if expect is not False:
        adjacent = ADJACENT_TYPES | ({"date"} if expect else frozenset())
        holes = pd.concat([_adjacent_holes(frame, keys, adjacent), _recurring_holes(frame, keys)])
        entity = [key for key in keys if key != "period_type"]
        holes = holes.drop_duplicates([*entity, "hole_year"])
        if len(holes):
            series = holes[entity].drop_duplicates().shape[0]
            items.append(
                ReviewItem(
                    dataset_id=config.dataset_id,
                    severity="warn",
                    kind="period_gap",
                    detail=(
                        f"{len(holes)} stretches where periods are absent between two that are "
                        f"present, in {series} series, e.g. {_examples(holes)}"
                    ),
                    count=len(holes),
                    suggestion=(
                        "confirm that the source omits these periods; absent rows are not flagged "
                        "on the value, so a total over the series would silently leave them out"
                    ),
                )
            )
    return items


def _examples(rows: pd.DataFrame) -> list[str]:
    pairs = rows["previous_label"].astype(str) + " -> " + rows["period_label"].astype(str)
    return list(dict.fromkeys(pairs))[:EXAMPLES]


def unverified_periods(config: SourceConfig, obs: pd.DataFrame) -> list[ReviewItem]:
    """Warn about yearly periods later than the last year whose window a person confirmed."""
    verified = config.period.verified_through
    if verified is None or obs.empty:
        return []
    yearly = obs.loc[obs["period_type"].isin(YEARLY_LABEL_TYPES) & obs["period_start"].notna()]
    first_year = pd.to_numeric(yearly["period_label"].astype(str).str.extract(r"^(\d{4})")[0])
    later = yearly.loc[first_year > verified]
    if later.empty:
        return []
    labels = sorted(set(later["period_label"].astype(str)))
    start_month = config.period.start_month
    window = (
        "calendar years" if start_month in (None, 1) else f"years starting in month {start_month}"
    )
    return [
        ReviewItem(
            dataset_id=config.dataset_id,
            severity="warn",
            kind="year_window_unverified",
            detail=(
                f"{len(labels)} periods after {verified} are dated as {window} "
                f"without confirmation, e.g. {labels[:EXAMPLES]}"
            ),
            count=len(later),
            suggestion=(
                "check the publisher's note for the new years; if the window changed, add a "
                "period.conventions entry; then raise period.verified_through"
            ),
        )
    ]
