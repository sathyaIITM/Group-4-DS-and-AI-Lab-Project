"""Kev decision questions (tool selection and domain) and the labelled-record contract.

The question text and option descriptions follow docs/labelling_guide_v1.md. Kev binds these
exact strings during fine-tuning, so training records and serving requests must both be built
from the constants below.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

GUIDE_VERSION = "1.0-draft.4"
STATE_CHAR_LIMIT = 1400  # about 384 tokens, the state length Kev-0.8B was mostly trained on

Tool = Literal[
    "run_sql",
    "make_chart",
    "describe_table",
    "search_catalog",
    "ask_clarification",
    "decline_not_covered",
]
Domain = Literal[
    "labour",
    "agriculture",
    "rainfall",
    "prices_economy",
    "health",
    "other",
    "multiple",
    "unspecified",
]
LabelSource = Literal["rule", "paraphrase", "teacher", "human"]
Split = Literal["train", "calibration", "dev_synthetic"]

TOOL_INSTRUCTIONS = (
    "Choose the next step of a data-analysis agent that answers questions about Indian public "
    "data using only the tables in the catalogue shown."
)
TOOL_OPTIONS: dict[str, str] = {
    "run_sql": (
        "Run a query: a quantitative question the catalogue can answer, with every required "
        "detail given or covered by a stated default."
    ),
    "make_chart": (
        "Draw or change a chart: a result table is already available and the user asks to plot "
        "or visualise it."
    ),
    "describe_table": (
        "Describe a catalogue table: its columns, units, coverage, definitions, spellings or "
        "method, without asking for a figure."
    ),
    "search_catalog": (
        "Search for data: the user asks which data or source exists on a topic, whether or not "
        "it is in the catalogue."
    ),
    "ask_clarification": (
        "Ask a clarifying question: the data is in the catalogue, but a required detail is "
        "missing with no default, or two readings give different answers."
    ),
    "decline_not_covered": (
        "Decline: the figure needs data absent from the catalogue, or the message is not a data "
        "request."
    ),
}

DOMAIN_INSTRUCTIONS = (
    "Which domain does the user's request concern? Use the domain of the measure the user asks for."
)
DOMAIN_OPTIONS: dict[str, str] = {
    "labour": "Employment, unemployment, labour force, wages and work.",
    "agriculture": "Crops, production, yield, area, minimum support prices and farm inputs.",
    "rainfall": "Rainfall, the monsoon and other weather measurements.",
    "prices_economy": "Prices, inflation, GDP, income, interest rates and other economic measures.",
    "health": "Health, nutrition, mortality, births and health services.",
    "other": "Any other topic, or a message that is not a data request.",
    "multiple": "Measures from two or more of the domains above, asked for on equal terms.",
    "unspecified": "A data request whose measure cannot be identified from the message or context.",
}

QUESTIONS: dict[str, tuple[str, dict[str, str]]] = {
    "tool": (TOOL_INSTRUCTIONS, TOOL_OPTIONS),
    "domain": (DOMAIN_INSTRUCTIONS, DOMAIN_OPTIONS),
}


class KevState(BaseModel):
    """What the router sees besides the questions; Kev renders field names visibly."""

    model_config = ConfigDict(extra="forbid")

    catalogue: str
    context: str
    user_message: str = Field(min_length=1)

    def rendered_length(self) -> int:
        """Characters of the `key: value` rendering Kev feeds the model."""
        return sum(len(f"{key}: {value}\n") for key, value in self.model_dump().items())


class ChoiceQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["choice"] = "choice"
    instructions: str
    criteria: dict[str, str]
    label: str


class RecordMeta(BaseModel):
    """Provenance for one record; Kev's loader keeps `_meta` and uses `group_id`."""

    model_config = ConfigDict(extra="forbid")

    id: str
    group_id: str
    split: Split | None = None
    label_source: LabelSource
    tool_rule: str
    domain_rule: str
    family: str
    template_id: str
    slots: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    has_result: bool
    domains: list[Domain] = Field(default_factory=list)  # every domain named, for `multiple`
    guide_version: str = GUIDE_VERSION
    generator: str
    seed: int
    human_checked: bool = False


class KevRecord(BaseModel):
    """One Kev training line: a System One request plus a label on each question."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    state: KevState
    questions: dict[str, ChoiceQuestion]
    meta: RecordMeta = Field(alias="_meta")

    @model_validator(mode="after")
    def _canonical(self) -> Self:
        if set(self.questions) != set(QUESTIONS):
            raise ValueError(f"questions must be exactly {sorted(QUESTIONS)}")
        for name, question in self.questions.items():
            instructions, criteria = QUESTIONS[name]
            if question.instructions != instructions or question.criteria != criteria:
                raise ValueError(f"question {name!r} differs from the canonical text")
            if question.label not in criteria:
                raise ValueError(f"label {question.label!r} is not an option of {name!r}")
        return self

    @property
    def tool(self) -> str:
        return self.questions["tool"].label

    @property
    def domain(self) -> str:
        return self.questions["domain"].label

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=True)


def render_context(
    has_result: bool, prior_turn: str | None = None, previous_tool: str | None = None
) -> str:
    if not has_result:
        return "No result table yet."
    return (
        f"A result table is available. Previous request: {prior_turn} "
        f"Previous tool: {previous_tool}."
    )


def build_record(state: KevState, tool: Tool, domain: Domain, meta: RecordMeta) -> KevRecord:
    questions = {
        name: ChoiceQuestion(instructions=instructions, criteria=criteria, label=label)
        for (name, (instructions, criteria)), label in zip(
            QUESTIONS.items(), (tool, domain), strict=True
        )
    }
    return KevRecord(state=state, questions=questions, meta=meta)


def serving_questions() -> dict[str, dict[str, object]]:
    """The `questions` object of a /v1/systemone request, identical to the training text."""
    return {
        name: {"type": "choice", "instructions": instructions, "criteria": criteria}
        for name, (instructions, criteria) in QUESTIONS.items()
    }
