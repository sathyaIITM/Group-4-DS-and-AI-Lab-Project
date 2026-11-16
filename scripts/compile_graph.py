from analyst.agents.graph import build_graph

graph = build_graph()

with open("../docs/figures/agent_graph.mmd", "w", encoding="utf-8") as f:
    f.write(graph.get_graph().draw_mermaid())