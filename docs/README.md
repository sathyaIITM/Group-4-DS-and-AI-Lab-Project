# Documents

## Milestone reports and slides

| Milestone | Report | Slides |
| --- | --- | --- |
| M1 Problem definition and literature review (22 October 2026) | [Milestone1_Report.md](milestones/Milestone1_Report.md); revised after the review: [Milestone1_Report_revised.pdf](milestones/Milestone1_Report_revised.pdf) | [Milestone1_TA_Presentation_revised.pptx](milestones/Milestone1_TA_Presentation_revised.pptx) |
| M2 Dataset identification and preparation (29 October 2026) | [Milestone2_Report.md](milestones/Milestone2_Report.md) | [Milestone2_TA_Presentation.pptx](milestones/Milestone2_TA_Presentation.pptx) |
| M3 Model architecture and end-to-end pipeline (5 November 2026) | [Milestone3_Report.md](milestones/Milestone3_Report.md) | [Milestone3_TA_Presentation.pptx](milestones/Milestone3_TA_Presentation.pptx) |
| M4 Model training, configuration and evaluation (19 November 2026) | [Milestone4_Report.md](milestones/Milestone4_Report.md) | [Milestone4_TA_Presentation.pptx](milestones/Milestone4_TA_Presentation.pptx) |

Figures used by the reports are in [milestones/figures/](milestones/figures/).

## Specifications

| Document | Content |
| --- | --- |
| [agent_graph.md](specs/agent_graph.md) | Design contract of the agent: nodes, edges, state, limits, outcome causes and guardrails |
| [agent_runtime_notes.md](specs/agent_runtime_notes.md) | Notes on the built agent: contracts, graph paths and counters |
| [data_contract_v1.md](specs/data_contract_v1.md) | Data contract 1.1: the fixed shape of every published table |
| [candidate_tables.md](specs/candidate_tables.md) | Source record of the catalogue tables and of the tables deferred |
| [catalogue_check.md](specs/catalogue_check.md) | Catalogue values traced back to the raw files (70 of 70) |
| [labelling_guide_v1.md](specs/labelling_guide_v1.md) | Labelling rules for the routing decisions (tool selection and domain) |
| [kev_training_protocol.md](specs/kev_training_protocol.md) | Kev-0.8B training protocol: runs, selection rule, records and review findings |
| [laya_feasibility_plan.md](specs/laya_feasibility_plan.md) | Plan for the Laya comparison |
| [run_log_v1.md](specs/run_log_v1.md), [run_bundle_v1.md](specs/run_bundle_v1.md) | Run log schema and exported run bundles |

## Internal reports

| Document | Content |
| --- | --- |
| [week1-feasibility.md](internal_reports/week1-feasibility.md) | Week-1 feasibility checks (23 October 2026); preliminary, superseded by the milestone reports |

## Conventions

Documents are formal and impersonal, without filler or contractions. Estimates are labelled as
estimates, and vendor or project benchmarks as self-reported. Every citation is checked against
its source.

The project is not presented as text-to-SQL research: a hosted LLM writes the queries, and SQL is
the execution layer. The retraining procedure is human-approved and is described as such, not as
a closed or self-improving loop.
