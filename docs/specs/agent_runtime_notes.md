# T2 runtime notes

Branch `fix/t2-graph-quickfix` (from `feature/t2-agent-graph` at `4f04a6b`).

## Contents
- Shared contracts: `src/analyst/contracts/`, field for field as in design document Section 4
  (`CONTRACT_VERSION = "1.0"`), with the T2 additions in `contracts/runtime.py`. The test
  `tests/test_contracts.py` fails when a contract's fields drift from the document.
- Graph: `agents/graph.py`. Routers only choose the next node; the cause of an abstention or a
  failure is derived inside the terminal node (`agents/control_nodes.py`). Every conditional edge and
  every edge that does not end in `finalize_response` applies the deadline, the LLM-call budget
  and `node_error` (`guarded`). `escalate_to_jev` lies between `route_tool_and_domain` and
  `resolve_routing_decision`.
- Counters are incremented by the node that performs the attempt (stubs and real nodes alike).
- Run log: `agents/runlog.py`, schema_version 1 (design document Section 9), written once by
  `finalize_response`; export with `python -m analyst.ops.export_runs`.
- Context retrieval (`agents/context.py`, `retrieve_context_and_examples`): tables, indicators and
  codelists from the published catalogue; cards at v1 and later, verified examples at v2 and
  later; file paths and fallbacks in `configs/agent.yaml` (`rag:`).
- T3 nodes: `agents/model_nodes.py` (`make_model_nodes`, `live_model_nodes`).

## Integration boundary
Stubs remain for the nodes of T4: `resolve_places_periods_units`, `validate_sql_with_sqlglot`,
`execute_read_only_duckdb`, `compute_derivations`, `deterministic_result_checks` and
`verify_numbers_deterministically`; and for T3's `verify_claim_support_and_intent`,
`calibrate_end_to_end_confidence` and `decide_answer_or_abstain`, which are pass-through in v0-v4.
Output of the stubs is not a result.

## Setup and checks
From the repository root: `python -m pip install -e ".[dev]"`, then `pytest -q`. The smoke command
`python scripts/run_agent.py --question "Show monthly rainfall in Kerala" --version v0` runs the
graph on stubs and makes no model call. `--llm live` connects T3's nodes to the hosted model.
