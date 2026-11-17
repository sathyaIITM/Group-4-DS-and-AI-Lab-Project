"""Print the stages visited by one run of the graph."""

from analyst.agents.graph import invoke_graph
from analyst.agents.state import AnalystState, RunConfig

state = invoke_graph(
    AnalystState(question="What is the unemployment rate in Kerala?", config=RunConfig())
)
print("Outcome:", state.outcome, "Cause:", state.outcome_cause)
print("Stages visited:")
for event in state.events:
    print(" ", event.stage)
