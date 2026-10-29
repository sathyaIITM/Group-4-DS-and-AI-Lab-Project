"""Tool-selection decision: one yes/no question per tool, argmax over the tools."""

from pydantic import BaseModel

from analyst.decisions.system_one import NoulQuestion, SystemOneClient

TOOLS: dict[str, str] = {
    "search_catalog": (
        "The user asks what data exists, which dataset or source covers a topic, "
        "or where data comes from, rather than asking for a number."
    ),
    "describe_table": (
        "The user asks about the structure or meaning of a table in the catalogue: "
        "columns, units, coverage, definitions or name spellings."
    ),
    "run_sql": (
        "The user asks a fully specified quantitative question that the tables in the "
        "catalogue can answer, and no result is available yet."
    ),
    "make_chart": (
        "A result table is already available and the user asks to plot, chart or "
        "visualise it, or to change the chart."
    ),
    "ask_clarification": (
        "The question concerns data in the catalogue, but a required detail (place, "
        "period, measure or definition) is missing or ambiguous and cannot be assumed."
    ),
    "decline_not_covered": (
        "The data needed is not in the catalogue, or the request is not a data question."
    ),
}

CATALOGUE = (
    "Catalogue (two tables):\n"
    "1. imd_subdivision_monthly_rainfall: IMD monthly rainfall in mm for 36 meteorological "
    "sub-divisions (not districts), calendar years 1901-2017; columns subdivision, year, "
    "jan..dec, annual, jf, mam, jjas, ond.\n"
    "2. plfs_state_ur_usual_status: PLFS unemployment rate in percent, usual status "
    "(principal + subsidiary), persons aged 15 and above, by State/UT plus an All India row, "
    "survey years 2017-18 to 2021-22 (one column per year).\n"
)

INSTRUCTION_TEMPLATE = (
    "Decide the next step of a data-analysis agent. Answer yes only if the next step is to "
    "call this tool: {tool}. Use when: {description}"
)


class RoutingExample(BaseModel):
    id: str
    question: str
    has_result: bool
    prior_turn: str | None = None
    label: str


class RoutingPrediction(BaseModel):
    id: str
    label: str
    predicted: str
    probabilities: dict[str, float]
    latency_s: float
    input_tokens: int = 0


def render_state(example: RoutingExample) -> str:
    """Everything the router sees for one example."""
    if example.has_result:
        context = f"A result table is available. Earlier turn: {example.prior_turn}\n"
    else:
        context = "No result table is available yet.\n"
    return f"{CATALOGUE}\n{context}\nUser message: {example.question}"


def tool_questions() -> dict[str, NoulQuestion]:
    return {
        tool: NoulQuestion(
            instructions=INSTRUCTION_TEMPLATE.format(tool=tool, description=description)
        )
        for tool, description in TOOLS.items()
    }


def route(client: SystemOneClient, example: RoutingExample) -> RoutingPrediction:
    """Ask every tool question in one call and take the highest yes-probability."""
    answer = client.ask(render_state(example), tool_questions())
    predicted = max(answer.probabilities, key=lambda name: answer.probabilities[name])
    return RoutingPrediction(
        id=example.id,
        label=example.label,
        predicted=predicted,
        probabilities=answer.probabilities,
        latency_s=answer.latency_s,
        input_tokens=answer.input_tokens,
    )


def to_training_record(example: RoutingExample) -> dict[str, object]:
    """One Kev training line: the routing request plus a true/false label per tool."""
    questions = {
        tool: {**question.model_dump(exclude_none=True), "label": tool == example.label}
        for tool, question in tool_questions().items()
    }
    return {"state": render_state(example), "questions": questions}
