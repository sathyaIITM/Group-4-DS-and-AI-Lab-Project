"""Generate rule-labelled Kev records for tool selection and domain.

Implements the programmatic core of the Kev data curation plan (Section 6.1): slots are sampled
from the catalogue, both labels are computed by the rules of docs/labelling_guide_v1.md, and the
rule ids are stored in `_meta`. A family is one base question plus its minimal-pair variants; all
records of a family share a `group_id` and therefore a split. Categories that wait for a guide
decision (Section 7 of the guide) are not generated.

Usage (from the repository root):
    python -m analyst.data.kev_generate --families 1000 --seed 13 --out-dir data/splits/kev
"""

import argparse
import hashlib
import json
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from analyst.data.catalogue import CATALOGUE_PATH, Catalogue, CatalogueTable, load_catalogue
from analyst.data.kev_checks import normalise
from analyst.decisions.kev_questions import (
    Domain,
    KevRecord,
    KevState,
    RecordMeta,
    Split,
    Tool,
    build_record,
    render_context,
)

GENERATOR = "kev_generate/0.3"
PLFS = "plfs_state_ur_usual_status"
IMD = "imd_subdivision_monthly_rainfall"
SPLIT_BOUNDS: tuple[tuple[Split, int], ...] = (
    ("train", 700),
    ("calibration", 840),
    ("dev_synthetic", 1000),
)
MONTHS = ["January", "March", "June", "July", "August", "September", "October", "December"]
SEASONS = {
    "jf": "January-February",
    "mam": "March-May",
    "jjas": "June-September",
    "ond": "October-December",
}

PLFS_TEMPLATES: dict[str, list[str]] = {
    "value": [
        "What was the unemployment rate in {place} in {period}?",
        "{place} unemployment rate {period}",
        "What was {place}'s jobless rate in {period}?",
        "How high was unemployment in {place} in {period}?",
    ],
    "hinglish": [
        "{place} mein {period} mein berozgari dar kitni thi?",
        "{period} mein {place} ki berozgari dar batao",
    ],
    "claim": [
        "Is it true that unemployment in {place} was {x}% in {period}?",
        "A news report says {place}'s unemployment rate was {x} percent in {period}. "
        "Is that correct?",
        "A politician claimed unemployment in {place} fell in {period}. Is that right?",
    ],
    "change": [
        "How did the unemployment rate in {place} change between {period} and {period2}?",
        "Did unemployment in {place} rise or fall from {period} to {period2}?",
    ],
    "compare": [
        "Compare the unemployment rate of {place} and {place2} in {period}.",
        "Was unemployment higher in {place} or {place2} in {period}?",
    ],
    "rank": [
        "Which state had the highest unemployment rate in {period}?",
        "List the five states with the lowest unemployment in {period}.",
        "Rank the states by unemployment rate for {period}.",
    ],
    "default_period": [
        "What is the unemployment rate in {place}?",
        "Latest unemployment figure for {place}?",
    ],
    "default_place": [
        "What was India's unemployment rate in {period}?",
        "What was the all-India unemployment rate in {period}?",
    ],
    "calendar_year": [
        "What was the unemployment rate in {place} in {cal_year}?",
        "{place} unemployment {cal_year}",
    ],
    "evaluative": [
        "Is unemployment high in {place}?",
        "Is {place}'s jobless rate high compared with earlier years?",
    ],
}
PLFS_SINGLE_PERIOD = {"value", "hinglish", "claim", "compare", "rank", "default_place"}
PLFS_BREAKDOWN = "What was the unemployment rate {breakdown} in {place} in {period}?"
PLFS_DEFINITION = "What was the unemployment rate in {place} in {period} {definition}?"
PLFS_GROUP = "What was the unemployment rate {group} in {place} in {period}?"
PLFS_CALENDAR = [
    "What was the unemployment rate in {place} for January to December {cal_year}?",
    "Unemployment in {place} for calendar year {cal_year}, Jan-Dec only",
]
ABSENT_TABLE = [
    "What columns does the {topic} dataset have?",
    "Which years does the {topic} data cover?",
    "What unit is the {topic} data reported in?",
]
CROSS_PERIOD = [
    "Compare {place}'s rainfall with its unemployment rate.",
    "Is rainfall linked to joblessness in {place}?",
    "Did a weak monsoon raise unemployment in {place}?",
]
CROSS_MEASURE = [
    "Compare the {phrase} and the unemployment rate in {state} in {year}.",
    "Did the {phrase} in {state} move with monsoon rainfall in {year}?",
]
CROSS_SEARCH = "Which datasets cover {topic} and {topic2}?"
CONTEXT_ONLY = "What was the {phrase} in {state} in the drought year {year}?"
NO_MEASURE = [
    "Top 5 please",
    "Rank them.",
    "Do the same for {place}.",
    "Is {place} doing better than {place2}?",
    "What about {place}?",
    "Show me the numbers for {place}.",
    "How did {place} do last year?",
    "Which state is the worst?",
    "Give me the figures for {place} and {place2}.",
    "Compare {place} with {place2}.",
    "Has it improved in {place}?",
    "Is {place} above the national average?",
    "Kya {place} mein haalat sudhri hai?",
    "Bottom three, please.",
    "Show the trend.",
    "What's the latest number?",
]
PLFS_SEARCH = [
    "Which datasets cover unemployment in {place}?",
    "Is there any data on jobs and unemployment for {place}?",
]

IMD_TEMPLATES: dict[str, list[str]] = {
    "annual": [
        "How much rain did {place} get in {year}?",
        "What was the annual rainfall in {place} in {year}?",
        "{place} rainfall {year}",
    ],
    "monsoon": [
        "What was the monsoon rainfall in {place} in {year}?",
        "How much rain fell in {place} during June-September {year}?",
    ],
    "month": ["How much rain did {place} receive in {month} {year}?"],
    "season": ["What was the {season_name} rainfall in {place} in {year}?"],
    "hinglish": [
        "{place} mein {year} mein kitni baarish hui?",
        "{year} ke monsoon mein {place} mein kitni barish hui?",
    ],
    "change": [
        "How did {place}'s monsoon rainfall in {year} compare with {year2}?",
        "Was {year} wetter than {year2} in {place}?",
    ],
    "trend": ["Show the trend in annual rainfall for {place} from {year} to {year2}."],
    "rank": [
        "Which sub-division received the least rainfall in {year}?",
        "Which part of the country was wettest in the {year} monsoon?",
        "Top five sub-divisions by annual rainfall in {year}?",
    ],
    "default_period": [
        "Rainfall in {place}",
        "What is the annual rainfall in {place}?",
    ],
}
IMD_PLACE_SINGLE_YEAR = {"annual", "monsoon", "month", "season", "hinglish"}
IMD_NO_PLACE = [
    "How much rain fell in {year}?",
    "What was the monsoon rainfall in India in {year}?",
]
IMD_FORECAST = [
    "Will {place} get a good monsoon next year?",
    "How much rain will {place} get in 2027?",
]
IMD_SEARCH = [
    "Is there any data on rainfall in {place}?",
    "Which dataset has monsoon rainfall for {place}?",
]

CHART_SHORT = [
    "Plot this.",
    "Can you show that as a bar chart?",
    "Chart these numbers.",
    "Show this on a graph.",
    "Visualise the result.",
    "Make a line chart of this.",
    "Ise graph mein dikhao.",
    "Put that in a chart please",
    "Graph it.",
    "Can I see this as a chart?",
    "Draw a bar graph of these values.",
    "Show me a trend line for this.",
    "A chart would help here.",
    "Plot these by year.",
    "Turn this table into a chart.",
    "Iska chart bana do.",
]
CHART_CHANGE = [
    "Make it a line chart instead.",
    "Switch to a bar chart.",
    "Add axis labels to the chart.",
    "Sort the bars from highest to lowest.",
    "Use a log scale on the chart.",
    "Make the chart horizontal.",
    "Change the title of the chart to something clearer.",
    "Show the values on top of the bars.",
    "Use a different colour for the bars.",
    "Remove the gridlines.",
]
MAX_FAMILIES_PER_GROUP = 6
FOLLOWUP_PLACE = [
    "And for {place2}?",
    "What about {place2}?",
    "Now compare it with {place2}.",
    "Same for {place2} please",
]
FOLLOWUP_PERIOD = ["What was it in {period2}?", "And in {period2}?"]
FOLLOWUP_PLOT = ["Plot the same for {place2}.", "Chart this for {place2} too."]

SEARCH_TEMPLATES = [
    "Which datasets cover {topic}?",
    "Is there any data on {topic}?",
    "Where can I find data about {topic} in India?",
    "Search for datasets about {topic}.",
    "What data do you have on {topic}?",
    "Which source publishes figures on {topic}?",
    "Is there any data on {topic} for {state}?",
]
UNCOVERED_TEMPLATES = [
    "What was the {phrase} in {state} in {year}?",
    "How did the {phrase} in {state} change between {year} and {year2}?",
    "Which state had the highest {phrase} in {year}?",
    "Is it true that the {phrase} in {state} doubled since {year}?",
    "{state} {phrase} {year}",
]
NON_DATA = [
    "Hi, how are you?",
    "Thanks, that is all I needed.",
    "Good morning!",
    "What is your name?",
    "Tell me a joke.",
    "Can you help me write a cover letter?",
    "What is the capital of Australia?",
    "Summarise today's news headlines.",
    "Book me a train ticket to Pune.",
    "Who will win the next Lok Sabha election?",
    "Which political party is best for jobs?",
    "Translate 'unemployment' into Tamil.",
    "Write a short poem about the monsoon.",
    "Recommend a good book on economics.",
    "Write an essay on the life of farmers.",
    "Ok",
    "Can you speak Hindi?",
    "Explain how you work.",
    "Please be quicker next time.",
    "Write a tweet about inflation.",
]
TOPIC_WORD_NON_DATA = {
    "Write a short poem about the monsoon.",
    "Recommend a good book on economics.",
    "Write an essay on the life of farmers.",
    "Write a tweet about inflation.",
}


@dataclass
class Draft:
    message: str
    tool: Tool
    domain: Domain
    tool_rule: str
    domain_rule: str
    template_id: str
    slots: dict[str, str]
    needs: str | None = None
    excludes: str | None = None
    has_result: bool = False
    prior_turn: str | None = None
    previous_tool: str | None = None
    tags: list[str] = field(default_factory=list)
    also: str | None = None  # a second table that must be shown
    domains: list[Domain] = field(default_factory=list)


class Families:
    """One method per family; each returns a base draft followed by its variants."""

    def __init__(self, catalogue: Catalogue, rng: random.Random) -> None:
        self.rng = rng
        self.plfs = catalogue.get(PLFS)
        self.imd = catalogue.get(IMD)
        self.uncovered = catalogue.uncovered
        self.states = self.plfs.places

    def _template(self, prefix: str, templates: dict[str, list[str]]) -> tuple[str, str, str]:
        kind = self.rng.choice(list(templates))
        index = self.rng.randrange(len(templates[kind]))
        return kind, templates[kind][index], f"{prefix}.{kind}.{index}"

    def _year(self) -> int:
        low = 1901 if self.rng.random() < 0.1 else 1980
        if self.imd.period_range is None:
            raise ValueError(f"{IMD} needs a period_range in the catalogue")
        return self.rng.randint(low, self.imd.period_range[1])

    def plfs_query(self) -> list[Draft]:
        rng, t = self.rng, self.plfs
        kind, template, tid = self._template("plfs", PLFS_TEMPLATES)
        place, place2 = rng.sample(t.places, 2)
        period, period2 = sorted(rng.sample(t.periods, 2))
        slots = {
            "place": place,
            "place2": place2,
            "period": period,
            "period2": period2,
            "x": f"{rng.uniform(1.5, 15):.1f}",
            "cal_year": str(rng.randint(2017, 2021)),
        }
        tags = ["hinglish"] if kind == "hinglish" else []
        if kind == "calendar_year":
            tags.append("year_type")
        if kind == "evaluative":
            tags.append("evaluative")
        if kind == "claim":
            tags.append("claim_check")
        if kind.startswith("default"):
            tags.append(kind)
        base = Draft(
            template.format(**slots),
            "run_sql",
            "labour",
            "R6",
            "M1",
            tid,
            slots,
            needs=PLFS,
            tags=tags,
        )
        drafts = [base]
        if rng.random() < 0.35:
            drafts.append(
                Draft(
                    base.message,
                    "decline_not_covered",
                    "labour",
                    "R7",
                    "M1",
                    tid,
                    slots,
                    excludes=PLFS,
                    tags=[*tags, "by_removal"],
                )
            )
        if kind in PLFS_SINGLE_PERIOD and rng.random() < 0.3:
            out = {**slots, "period": rng.choice(t.out_of_range_periods)}
            drafts.append(
                Draft(
                    template.format(**out),
                    "decline_not_covered",
                    "labour",
                    "R8",
                    "M1",
                    tid,
                    out,
                    needs=PLFS,
                    tags=[*tags, "out_of_range"],
                )
            )
        if kind == "value":
            variant = rng.random()
            if variant < 0.3:
                extra = {**slots, "breakdown": rng.choice(t.absent_breakdowns)}
                drafts.append(
                    Draft(
                        PLFS_BREAKDOWN.format(**extra),
                        "decline_not_covered",
                        "labour",
                        "R9",
                        "M1",
                        "plfs.breakdown.0",
                        extra,
                        needs=PLFS,
                        tags=["absent_breakdown"],
                    )
                )
            elif variant < 0.45:
                extra = {**slots, "group": rng.choice(t.lacking_groups)}
                drafts.append(
                    Draft(
                        PLFS_GROUP.format(**extra),
                        "ask_clarification",
                        "labour",
                        "R12",
                        "M1",
                        "plfs.group.0",
                        extra,
                        needs=PLFS,
                        tags=["lacking_group"],
                    )
                )
            elif variant < 0.6:
                extra = {**slots, "definition": rng.choice(t.lacking_definitions)}
                drafts.append(
                    Draft(
                        PLFS_DEFINITION.format(**extra),
                        "ask_clarification",
                        "labour",
                        "R12",
                        "M1",
                        "plfs.definition.0",
                        extra,
                        needs=PLFS,
                        tags=["lacking_definition"],
                    )
                )
            elif variant < 0.8:
                index = rng.randrange(len(PLFS_SEARCH))
                drafts.append(
                    Draft(
                        PLFS_SEARCH[index].format(**slots),
                        "search_catalog",
                        "labour",
                        "R2",
                        "M2",
                        f"plfs.search.{index}",
                        slots,
                    )
                )
        return drafts

    def imd_query(self) -> list[Draft]:
        rng, t = self.rng, self.imd
        kind, template, tid = self._template("imd", IMD_TEMPLATES)
        year = self._year()
        year2 = self._year()
        while year2 == year:
            year2 = self._year()
        season = rng.choice(list(SEASONS))
        slots = {
            "place": rng.choice(t.places),
            "year": str(min(year, year2)),
            "year2": str(max(year, year2)),
            "month": rng.choice(MONTHS),
            "season_name": SEASONS[season],
        }
        tags = ["hinglish"] if kind == "hinglish" else []
        if kind == "default_period":
            tags.append(kind)
        base = Draft(
            template.format(**slots),
            "run_sql",
            "rainfall",
            "R6",
            "M1",
            tid,
            slots,
            needs=IMD,
            tags=tags,
        )
        drafts = [base]
        if rng.random() < 0.3:
            drafts.append(
                Draft(
                    base.message,
                    "decline_not_covered",
                    "rainfall",
                    "R7",
                    "M1",
                    tid,
                    slots,
                    excludes=IMD,
                    tags=[*tags, "by_removal"],
                )
            )
        if kind == "rank":
            return drafts
        variant = rng.random()
        if kind in IMD_PLACE_SINGLE_YEAR and variant < 0.25:
            multi = {**slots, "place": rng.choice(list(t.multi_places))}
            drafts.append(
                Draft(
                    template.format(**multi),
                    "run_sql",
                    "rainfall",
                    "R11",
                    "M1",
                    tid,
                    multi,
                    needs=IMD,
                    tags=[*tags, "multi_place"],
                )
            )
        elif kind in IMD_PLACE_SINGLE_YEAR and variant < 0.45:
            index = rng.randrange(len(IMD_NO_PLACE))
            drafts.append(
                Draft(
                    IMD_NO_PLACE[index].format(**slots),
                    "ask_clarification",
                    "rainfall",
                    "R10",
                    "M1",
                    f"imd.no_place.{index}",
                    slots,
                    needs=IMD,
                    tags=["no_national_row"],
                )
            )
        elif kind in IMD_PLACE_SINGLE_YEAR and variant < 0.6:
            out = {**slots, "year": rng.choice(t.out_of_range_periods)}
            drafts.append(
                Draft(
                    template.format(**out),
                    "decline_not_covered",
                    "rainfall",
                    "R8",
                    "M1",
                    tid,
                    out,
                    needs=IMD,
                    tags=[*tags, "out_of_range"],
                )
            )
        elif kind in IMD_PLACE_SINGLE_YEAR and variant < 0.72:
            district = {**slots, "place": rng.choice(t.absent_breakdowns)}
            drafts.append(
                Draft(
                    template.format(**district),
                    "decline_not_covered",
                    "rainfall",
                    "R9",
                    "M1",
                    tid,
                    district,
                    needs=IMD,
                    tags=[*tags, "absent_breakdown"],
                )
            )
        elif variant < 0.8:
            alias, _ = rng.choice(list(t.place_aliases.items()))
            renamed = {**slots, "place": alias}
            drafts.append(
                Draft(
                    template.format(**renamed),
                    "run_sql",
                    "rainfall",
                    "R6",
                    "M1",
                    tid,
                    renamed,
                    needs=IMD,
                    tags=[*tags, "name_variant"],
                )
            )
        elif variant < 0.88:
            index = rng.randrange(len(IMD_FORECAST))
            drafts.append(
                Draft(
                    IMD_FORECAST[index].format(**slots),
                    "decline_not_covered",
                    "rainfall",
                    "R8",
                    "M1",
                    f"imd.forecast.{index}",
                    slots,
                    needs=IMD,
                    tags=["forecast"],
                )
            )
        elif variant < 0.96:
            index = rng.randrange(len(IMD_SEARCH))
            drafts.append(
                Draft(
                    IMD_SEARCH[index].format(**slots),
                    "search_catalog",
                    "rainfall",
                    "R2",
                    "M2",
                    f"imd.search.{index}",
                    slots,
                )
            )
        return drafts

    def clarify(self) -> list[Draft]:
        """Clarification bases (R10, R12, R14), sometimes paired with the resolved question."""
        rng, t = self.rng, self.plfs
        roll = rng.random()
        if roll < 0.3:
            index = rng.randrange(len(IMD_NO_PLACE))
            slots = {"year": str(self._year())}
            return [
                Draft(
                    IMD_NO_PLACE[index].format(**slots),
                    "ask_clarification",
                    "rainfall",
                    "R10",
                    "M1",
                    f"imd.no_place.{index}",
                    slots,
                    needs=IMD,
                    tags=["no_national_row"],
                )
            ]
        slots = {
            "place": rng.choice(t.places),
            "period": rng.choice(t.periods),
            "cal_year": str(rng.randint(2017, 2021)),
            "definition": rng.choice(t.lacking_definitions),
            "group": rng.choice(t.lacking_groups),
        }
        if roll < 0.55:
            message, tid, rule, tag = (
                PLFS_GROUP.format(**slots),
                "plfs.group.0",
                "R12",
                "lacking_group",
            )
        elif roll < 0.75:
            index = rng.randrange(len(PLFS_CALENDAR))
            message, tid = PLFS_CALENDAR[index].format(**slots), f"plfs.calendar.{index}"
            rule, tag = "R14", "year_type"
        else:
            message, tid = PLFS_DEFINITION.format(**slots), "plfs.definition.0"
            rule, tag = "R12", "lacking_definition"
        drafts = [
            Draft(
                message,
                "ask_clarification",
                "labour",
                rule,
                "M1",
                tid,
                slots,
                needs=PLFS,
                tags=[tag],
            )
        ]
        if rng.random() < 0.25:
            # Minimal pair: the same question without the detail the table lacks.
            if rule == "R14":
                value = (
                    f"What was the unemployment rate in {slots['place']} in {slots['cal_year']}?"
                )
                pair_rule, pair_tags = "R6", ["year_type"]
            else:
                value = f"What was the unemployment rate in {slots['place']} in {slots['period']}?"
                pair_rule, pair_tags = "R6", []
            drafts.append(
                Draft(
                    value,
                    "run_sql",
                    "labour",
                    pair_rule,
                    "M1",
                    f"{tid}.pair",
                    slots,
                    needs=PLFS,
                    tags=pair_tags,
                )
            )
        return drafts

    def no_measure(self) -> list[Draft]:
        """No measure identifiable (decision H2): clarify, domain `unspecified`. Paired with the
        same message after a result, where the result supplies the measure (R13, M4)."""
        rng = self.rng
        index = rng.randrange(len(NO_MEASURE))
        place, place2 = rng.sample(sorted(set(self.plfs.places) & set(self.imd.places)), 2)
        slots = {"place": place, "place2": place2}
        message = NO_MEASURE[index].format(**slots)
        tid = f"no_measure.{index}"
        drafts = [
            Draft(
                message,
                "ask_clarification",
                "unspecified",
                "R10",
                "M8",
                tid,
                slots,
                tags=["no_measure"],
            )
        ]
        if rng.random() < 0.4:
            table, domain, _, _, prior = self._result()
            drafts.append(
                Draft(
                    message,
                    "run_sql",
                    domain,
                    "R13",
                    "M4",
                    tid,
                    slots,
                    needs=table,
                    has_result=True,
                    prior_turn=f"The user asked for {prior}",
                    previous_tool="run_sql",
                    tags=["follow_up"],
                )
            )
        return drafts

    def absent_table(self) -> list[Draft]:
        """A question about a table that is not in the catalogue (decision H9)."""
        rng = self.rng
        measure = rng.choice(self.uncovered)
        index = rng.randrange(len(ABSENT_TABLE))
        slots = {"topic": measure.topic}
        message = ABSENT_TABLE[index].format(**slots)
        if measure.domain == "other":
            return [
                Draft(
                    message,
                    "decline_not_covered",
                    "other",
                    "R15",
                    "M6",
                    f"absent_table.{index}",
                    slots,
                    tags=["absent_table"],
                )
            ]
        return [
            Draft(
                message,
                "search_catalog",
                measure.domain,
                "R15",
                "M2",
                f"absent_table.{index}",
                slots,
                tags=["absent_table"],
            )
        ]

    def cross_domain(self) -> list[Draft]:
        """Measures from two domains on equal terms (`multiple`, decisions H3 and H4)."""
        rng = self.rng
        roll = rng.random()
        if roll < 0.35:
            index = rng.randrange(len(CROSS_PERIOD))
            place = rng.choice(sorted(set(self.plfs.places) & set(self.imd.places)))
            slots = {"place": place}
            return [
                Draft(
                    CROSS_PERIOD[index].format(**slots),
                    "decline_not_covered",
                    "multiple",
                    "R16",
                    "M7",
                    f"cross.period.{index}",
                    slots,
                    needs=PLFS,
                    also=IMD,
                    domains=["labour", "rainfall"],
                    tags=["period_mismatch"],
                )
            ]
        in_domain = [m for m in self.uncovered if m.domain not in {"labour", "rainfall", "other"}]
        measure = rng.choice(in_domain)
        year = str(rng.randint(2012, 2021))
        state = rng.choice(self.states)
        slots = {"phrase": measure.phrase, "state": state, "year": year}
        if roll < 0.75:
            index = rng.randrange(len(CROSS_MEASURE))
            other: Domain = "labour" if index == 0 else "rainfall"
            drafts = [
                Draft(
                    CROSS_MEASURE[index].format(**slots),
                    "decline_not_covered",
                    "multiple",
                    "R7",
                    "M7",
                    f"cross.measure.{index}",
                    slots,
                    domains=[measure.domain, other],
                    tags=["cross_measure"],
                )
            ]
            if rng.random() < 0.4:
                # Tie-break pair: the second domain only as context, so one domain.
                drafts.append(
                    Draft(
                        CONTEXT_ONLY.format(**slots),
                        "decline_not_covered",
                        measure.domain,
                        "R7",
                        "M1",
                        "cross.context_only",
                        slots,
                        tags=["context_domain"],
                    )
                )
            return drafts
        second = rng.choice(
            [m for m in self.uncovered if m.domain not in {measure.domain, "other"}]
        )
        slots = {"topic": measure.topic, "topic2": second.topic}
        return [
            Draft(
                CROSS_SEARCH.format(**slots),
                "search_catalog",
                "multiple",
                "R2",
                "M7",
                "cross.search",
                slots,
                domains=[measure.domain, second.domain],
            )
        ]

    def _result(self) -> tuple[str, Domain, dict[str, str], str, str]:
        """A prior request with a multi-row result: (table, domain, slots, request, prior)."""
        rng = self.rng
        if rng.random() < 0.5:
            place, place2 = rng.sample(self.plfs.places, 2)
            slots = {"place": place, "place2": place2, "period2": rng.choice(self.plfs.periods)}
            request = f"Plot the unemployment rate in {place} from 2017-18 to 2021-22."
            prior = (
                f"the unemployment rate in {place}, 2017-18 to 2021-22; a 5-row result "
                "table was returned."
            )
            return PLFS, "labour", slots, request, prior
        place, place2 = rng.sample(self.imd.places, 2)
        start = rng.randint(1990, 2010)
        end = rng.randint(start + 3, 2017)
        slots = {"place": place, "place2": place2, "period2": str(rng.randint(1990, 2017))}
        request = f"Plot the annual rainfall in {place} from {start} to {end}."
        prior = (
            f"annual rainfall in {place}, {start} to {end}; a {end - start + 1}-row result "
            "table was returned."
        )
        slots |= {"start": str(start), "end": str(end)}
        return IMD, "rainfall", slots, request, prior

    def chart(self) -> list[Draft]:
        rng = self.rng
        table, domain, slots, request, prior = self._result()
        if rng.random() < 0.3:
            # Minimal pair (R4 against R5): the same request with and without a result.
            tid = f"chart.spec.{table}"
            return [
                Draft(
                    request,
                    "run_sql",
                    domain,
                    "R5",
                    "M1",
                    tid,
                    slots,
                    needs=table,
                    tags=["plot_without_result"],
                ),
                Draft(
                    request,
                    "make_chart",
                    domain,
                    "R4",
                    "M4",
                    tid,
                    slots,
                    needs=table,
                    has_result=True,
                    prior_turn=f"The user asked for {prior}",
                    previous_tool="run_sql",
                ),
            ]
        change = rng.random() < 0.35
        pool = CHART_CHANGE if change else CHART_SHORT
        index = rng.randrange(len(pool))
        tid = f"chart.{'change' if change else 'short'}.{index}"
        previous = "make_chart" if change else "run_sql"
        slots = {**slots, "message": pool[index]}
        return [
            Draft(
                pool[index],
                "make_chart",
                domain,
                "R4",
                "M4",
                tid,
                slots,
                needs=table,
                has_result=True,
                prior_turn=f"The user asked for {prior}",
                previous_tool=previous,
                tags=["chart_change"] if change else [],
            )
        ]

    def followup(self) -> list[Draft]:
        rng = self.rng
        table, domain, slots, _, prior = self._result()
        pools = {"place": FOLLOWUP_PLACE, "period": FOLLOWUP_PERIOD, "plot": FOLLOWUP_PLOT}
        kind = rng.choice(list(pools))
        index = rng.randrange(len(pools[kind]))
        tags = ["follow_up", "plot_followup"] if kind == "plot" else ["follow_up"]
        return [
            Draft(
                pools[kind][index].format(**slots),
                "run_sql",
                domain,
                "R13",
                "M4",
                f"followup.{kind}.{index}",
                slots,
                needs=table,
                has_result=True,
                prior_turn=f"The user asked for {prior}",
                previous_tool=rng.choice(["run_sql", "make_chart"]),
                tags=tags,
            )
        ]

    def describe(self) -> list[Draft]:
        rng = self.rng
        t: CatalogueTable = rng.choice([self.plfs, self.imd])
        if rng.random() < 0.3:
            index = rng.randrange(len(t.describe_questions))
            return [
                Draft(
                    t.describe_questions[index],
                    "describe_table",
                    t.domain,
                    "R3",
                    "M3",
                    f"describe.{t.name}.fixed.{index}",
                    {},
                    needs=t.name,
                )
            ]
        index = rng.randrange(len(t.describe_templates))
        slots = {
            "place": rng.choice(t.places),
            "season": rng.choice(list(SEASONS)),
            "state": rng.choice([*t.multi_places, *t.place_aliases] or t.places),
        }
        tid = f"describe.{t.name}.template.{index}"
        drafts = [
            Draft(
                t.describe_templates[index].format(**slots),
                "describe_table",
                t.domain,
                "R3",
                "M3",
                tid,
                slots,
                needs=t.name,
            )
        ]
        if rng.random() < 0.25:
            # Minimal pair (R3 against R6): ask for the value instead of the table's coverage.
            if t.name == PLFS:
                period = rng.choice(t.periods)
                value = f"What was the unemployment rate in {slots['place']} in {period}?"
            else:
                period = str(self._year())
                value = f"How much rain did {slots['place']} get in {period}?"
            drafts.append(
                Draft(
                    value,
                    "run_sql",
                    t.domain,
                    "R6",
                    "M1",
                    f"{tid}.value",
                    {**slots, "period": period},
                    needs=t.name,
                )
            )
        return drafts

    def search(self) -> list[Draft]:
        rng = self.rng
        measure = rng.choice(self.uncovered)
        index = rng.randrange(len(SEARCH_TEMPLATES))
        year = str(rng.randint(2012, 2023))
        slots = {"topic": measure.topic, "state": rng.choice(self.states), "year": year}
        rule = "M6" if measure.domain == "other" else "M2"
        drafts = [
            Draft(
                SEARCH_TEMPLATES[index].format(**slots),
                "search_catalog",
                measure.domain,
                "R2",
                rule,
                f"search.{index}",
                slots,
            )
        ]
        if rng.random() < 0.4:
            # Minimal pair (R2 against R7): ask for the figure instead of the dataset.
            value = f"What was the {measure.phrase} in {slots['state']} in {year}?"
            drafts.append(
                Draft(
                    value,
                    "decline_not_covered",
                    measure.domain,
                    "R7",
                    "M6" if measure.domain == "other" else "M1",
                    "search.value",
                    {**slots, "phrase": measure.phrase},
                )
            )
        return drafts

    def uncovered_query(self) -> list[Draft]:
        rng = self.rng
        measure = rng.choice(self.uncovered)
        index = rng.randrange(len(UNCOVERED_TEMPLATES))
        year = rng.randint(2012, 2021)
        slots = {
            "phrase": measure.phrase,
            "state": rng.choice(self.states),
            "year": str(year),
            "year2": str(rng.randint(year + 1, 2023)),
        }
        rule = "M6" if measure.domain == "other" else "M1"
        return [
            Draft(
                UNCOVERED_TEMPLATES[index].format(**slots),
                "decline_not_covered",
                measure.domain,
                "R7",
                rule,
                f"uncovered.{index}",
                slots,
            )
        ]

    def non_data(self) -> list[Draft]:
        index = self.rng.randrange(len(NON_DATA))
        message = NON_DATA[index]
        tags = ["topic_word"] if message in TOPIC_WORD_NON_DATA else []
        return [
            Draft(
                message,
                "decline_not_covered",
                "other",
                "R1",
                "M5",
                f"non_data.{index}",
                {},
                tags=tags,
            )
        ]


def family_weights(families: Families) -> dict[str, tuple[Callable[[], list[Draft]], float]]:
    return {
        "plfs_query": (families.plfs_query, 0.07),
        "imd_query": (families.imd_query, 0.07),
        "clarify": (families.clarify, 0.15),
        "chart": (families.chart, 0.17),
        "followup": (families.followup, 0.04),
        "describe": (families.describe, 0.17),
        "absent_table": (families.absent_table, 0.04),
        "no_measure": (families.no_measure, 0.08),
        "cross_domain": (families.cross_domain, 0.07),
        "search": (families.search, 0.12),
        "uncovered_query": (families.uncovered_query, 0.07),
        "non_data": (families.non_data, 0.05),
    }


def group_id(family: str, draft: Draft) -> str:
    """Template id plus the normalised base message (digits mapped to 0), so variants that
    differ only in a year or a number share a group and therefore a split."""
    key = json.dumps([draft.template_id, normalise(draft.message)])
    return f"{family}:{hashlib.sha256(key.encode()).hexdigest()[:12]}"


def split_of(group: str) -> Split:
    bucket = int(hashlib.sha256(group.encode()).hexdigest(), 16) % 1000
    return next(name for name, bound in SPLIT_BOUNDS if bucket < bound)


def surface(rng: random.Random, drafts: list[Draft]) -> None:
    """Family-wide surface noise, applied identically to every draft of the family."""
    roll = rng.random()
    if roll < 0.12:
        for d in drafts:
            d.message, d.tags = d.message.lower(), [*d.tags, "lowercase"]
    elif roll < 0.22:
        for d in drafts:
            d.message, d.tags = d.message.rstrip("?."), [*d.tags, "no_punct"]
    elif roll < 0.28 and len(drafts) == 1:
        words = drafts[0].message.split()
        long = [i for i, w in enumerate(words) if len(w) > 5 and w.isalpha()]
        if long:
            i = rng.choice(long)
            j = rng.randrange(1, len(words[i]) - 2)
            w = words[i]
            words[i] = w[:j] + w[j + 1] + w[j] + w[j + 2 :]
            drafts[0].message, drafts[0].tags = " ".join(words), [*drafts[0].tags, "typo"]


def catalogue_text(
    rng: random.Random, tables: list[CatalogueTable], needs: set[str], excludes: str | None
) -> str:
    pool = [t for t in tables if t.name != excludes]
    chosen = [t for t in pool if t.name in needs or rng.random() < 0.6] or [rng.choice(pool)]
    rng.shuffle(chosen)
    return "\n".join(f"{i}. {t.line}" for i, t in enumerate(chosen, start=1))


def generate(catalogue: Catalogue, n_families: int, seed: int) -> list[KevRecord]:
    rng = random.Random(seed)  # noqa: S311 - reproducible sampling, not security
    families = Families(catalogue, rng)
    weights = family_weights(families)
    names = list(weights)
    tables = catalogue.real_tables()
    seen: set[str] = set()
    per_group: Counter[str] = Counter()
    accepted: list[tuple[str, str, list[Draft]]] = []
    attempts = 0
    while len(seen) < n_families and attempts < n_families * 20:
        attempts += 1
        name = rng.choices(names, weights=[w for _, w in weights.values()])[0]
        drafts = weights[name][0]()
        group = group_id(name, drafts[0])
        # A short command ("Plot this.") recurs with different prior results: one family per
        # prior, capped per message.
        key = f"{group}|{drafts[0].prior_turn}"
        if key in seen or per_group[group] >= MAX_FAMILIES_PER_GROUP:
            continue
        seen.add(key)
        per_group[group] += 1
        accepted.append((name, group, drafts))

    # A message can be the base of one family and a variant in another. Families that share
    # any normalised message are merged, so that message never sits in two splits.
    parent = list(range(len(accepted)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner: dict[str, int] = {}
    for i, (_, _, drafts) in enumerate(accepted):
        for draft in drafts:
            text = normalise(draft.message)
            if text in owner:
                parent[find(i)] = find(owner[text])
            else:
                owner[text] = i
    merged: dict[int, str] = {}
    for i, (_, group, _) in enumerate(accepted):
        root = find(i)
        merged[root] = min(merged.get(root, group), group)

    records: list[KevRecord] = []
    for i, (name, _, drafts) in enumerate(accepted):
        group = merged[find(i)]
        split = split_of(group)
        surface(rng, drafts)
        for draft in drafts:
            state = KevState(
                catalogue=catalogue_text(
                    rng, tables, {n for n in (draft.needs, draft.also) if n}, draft.excludes
                ),
                context=render_context(draft.has_result, draft.prior_turn, draft.previous_tool),
                user_message=draft.message,
            )
            meta = RecordMeta(
                id=f"gen1-{len(records):05d}",
                group_id=group,
                split=split,
                label_source="rule",
                tool_rule=draft.tool_rule,
                domain_rule=draft.domain_rule,
                family=name,
                template_id=draft.template_id,
                slots=draft.slots,
                tags=draft.tags,
                has_result=draft.has_result,
                domains=draft.domains,
                generator=GENERATOR,
                seed=seed,
            )
            records.append(build_record(state, draft.tool, draft.domain, meta))
    return records


def write_splits(records: list[KevRecord], out_dir: Path, version: int) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for split, _ in SPLIT_BOUNDS:
        path = out_dir / f"{split}.v{version}.jsonl"
        rows = [r.to_json() for r in records if r.meta.split == split]
        path.write_text("\n".join(rows) + "\n")
        paths[split] = path
    return paths


def summary(records: list[KevRecord]) -> str:
    lines = []
    for split, _ in SPLIT_BOUNDS:
        part = [r for r in records if r.meta.split == split]
        groups = len({r.meta.group_id for r in part})
        lines.append(f"{split}: {len(part)} records, {groups} groups")
        for question in ("tool", "domain"):
            counts = Counter(r.questions[question].label for r in part)
            shares = ", ".join(f"{k} {v} ({v / len(part):.0%})" for k, v in counts.most_common())
            lines.append(f"  {question}: {shares}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate rule-labelled Kev records.")
    parser.add_argument("--catalogue", type=Path, default=CATALOGUE_PATH)
    parser.add_argument("--families", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--out-dir", type=Path, default=Path("data/splits/kev"))
    args = parser.parse_args()
    records = generate(load_catalogue(args.catalogue), args.families, args.seed)
    for split, path in write_splits(records, args.out_dir, args.version).items():
        print(f"wrote {path} ({split})")
    print(summary(records))


if __name__ == "__main__":
    main()
