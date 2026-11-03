"""Registry of source-specific rules: the only table-specific code in the pipeline.

A rule is allowed only when a defect or convention cannot be expressed in a
configuration. Each entry carries its evidence and the number of values it was
observed to change, and has a test. Detection of the problem stays generic (for
example, a column declared non-negative that holds negatives is flagged for any
table); only the *interpretation* lives here.
"""

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from analyst.data.contract import Flag

# fn(token, numeric_text, flag, rule) edits ``numeric_text``, ``flag`` and ``rule`` in place.
RuleFn = Callable[[pd.Series, pd.Series, pd.Series, pd.Series], None]


@dataclass(frozen=True)
class SourceRule:
    id: str
    description: str
    evidence: str
    observed_values: int
    fn: RuleFn


RULES: dict[str, SourceRule] = {}


def register(rule: SourceRule) -> SourceRule:
    if rule.id in RULES:
        msg = f"source rule {rule.id!r} is already registered"
        raise ValueError(msg)
    RULES[rule.id] = rule
    return rule


def _nfhs5_minus_as_low_sample(
    token: pd.Series, numeric_text: pd.Series, flag: pd.Series, rule: pd.Series
) -> None:
    mask = flag.isna() & token.str.match(r"^-\d", na=False)
    numeric_text.loc[mask] = token.loc[mask].str[1:]
    flag.loc[mask] = Flag.LOW_SAMPLE_ESTIMATE.value
    rule.loc[mask] = rule.loc[mask].map(lambda r: f"{r};nfhs5_minus_as_low_sample".lstrip(";"))


register(
    SourceRule(
        id="nfhs5_minus_as_low_sample",
        description=(
            "The NFHS-5 factsheet prints estimates based on 25-49 unweighted cases in "
            "parentheses, e.g. (29.5). The data.gov.in API export renders them as -29.5. "
            "No NFHS-5 indicator can be negative, so a leading minus is the low-sample marker."
        ),
        evidence=(
            "Download of 2026-10-29: 4,884 negative cells, including vaccination coverage "
            "-100 and out-of-pocket expenditure -10,557 rupees; none remain after the rule."
        ),
        observed_values=4884,
        fn=_nfhs5_minus_as_low_sample,
    )
)
