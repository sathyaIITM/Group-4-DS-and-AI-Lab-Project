# Documents

| Document | Status |
| --- | --- |
| [Milestone1_Report.md](milestones/Milestone1_Report.md) | Current. Milestone 1: problem definition and literature review, condensed submission version, revised 2026-10-22 |
| [Milestone2_Report.md](milestones/Milestone2_Report.md) | Current. Milestone 2: dataset identification and data preparation, 29 October 2026 |
| [agent_graph.md](specs/agent_graph.md) | Version 0.3, 2026-11-05. LangGraph agent specification: nodes, edges, state, limits, outcome causes, query-intent extraction, internal tools, guardrails and offline procedures (input to Milestone 3) |
| [labelling_guide_v1.md](specs/labelling_guide_v1.md) | Current. Labelling rules for the routing decisions (tool selection and domain) |
| [Architecture_Diagram.svg](milestones/figures/Architecture_Diagram.svg) | Current. Figure 1 of the Milestone 1 report |
| [Milestone_1_TA_Presentation.pptx](milestones/Milestone_1_TA_Presentation.pptx) | Current. TA review deck for Milestone 1, aligned to the report above |
| [Milestone1_TA_Presentation_revised.pptx](milestones/Milestone1_TA_Presentation_revised.pptx), [Milestone1_Report_revised.pdf](milestones/Milestone1_Report_revised.pdf) | Milestone 1 deck and report as revised after the TA review |
| [Milestone2_TA_Presentation.pptx](milestones/Milestone2_TA_Presentation.pptx) | Milestone 2 deck, version 1.1, 3 November 2026 |
| [Milestone3_Report.md](milestones/Milestone3_Report.md) | Current. Milestone 3: model architecture and end-to-end pipeline design, version 1.1, 5 November 2026 |
| [Milestone3_TA_Presentation.pptx](milestones/Milestone3_TA_Presentation.pptx) | Milestone 3 deck, 5 November 2026 |
| [milestones/figures/](milestones/figures/) | Figures of the milestone reports |
| [candidate_tables.md](specs/candidate_tables.md) | Source record of the T1 candidate tables, 5 November 2026 |

Earlier drafts and the pre-2026-10-22 team review note are kept on the
author's machine for reference, not in this repository.

The authored copies of the Milestone 1 report are drafting documents held
privately by their author (condensed submission version, full version 2 with
43 verified references, and version 1 retained for reversion). Their links are
kept with the author's own project notes, outside this repository.

## Conventions

Documents are formal, crisp and impersonal: no filler, contractions or
rhetorical framing. Estimates are labelled as estimates and vendor or project
benchmarks as self-reported. Every citation is checked against its source.

Two framings are fixed. The project is not presented as text-to-SQL research: a
hosted LLM writes the queries and SQL is only the execution layer. The
retraining procedure is human-approved, so it is described as a
"human-approved retraining procedure", never as a closed or self-improving
loop.
