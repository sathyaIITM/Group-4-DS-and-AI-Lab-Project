# run_graph.py

from analyst.agents.graph import build_graph
from analyst.agents.state import AnalystState, RunConfig

graph = build_graph()

state = AnalystState(
    question="What is the unemployment rate in Kerala?",
    config=RunConfig(version="v0"),
)

result = graph.invoke(state.model_dump())

print("Outcome:", result.get("outcome"))
print("Cause:", result.get("outcome_cause"))

print("\nStages visited:")
for event in result.get("events", []):
    print(event.stage)