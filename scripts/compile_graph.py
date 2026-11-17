"""Write the Mermaid diagram of the compiled graph to docs/milestones/figures/agent_graph.mmd."""

from pathlib import Path

from analyst.agents.graph import build_graph

target = Path("docs/milestones/figures/agent_graph.mmd")
target.write_text(build_graph().get_graph().draw_mermaid(), encoding="utf-8")
print(f"wrote {target}")
