# T2 runtime implementation notes

## Included in this implementation pass
- Shared frozen Pydantic contracts in `src/analyst/contracts/`.
- `AnalystState` imports the shared contracts instead of defining duplicate placeholder
  data models.
- YAML-backed `RunConfig.from_files(version)` with configuration hashes.
- SQLite conversation memory and run logging.
- Evidence bundle persistence and current-version validation.
- Result-driven chart selection and Vega-Lite specification generation.
- Catalogue description, lexical listing and explanation helpers.
- Parquet run export with a SHA-256 manifest.
- T2-owned intake, screening, lexical catalogue retrieval, narrow router-decline rule,
  metadata description, catalogue search, evidence explanation, evidence construction,
  chart selection and finalization nodes wired into the graph.
- Scripted fake LLM, decision, index and tool clients for deterministic tests.
- CLI entry point accepting `--question` or JSONL `--file`.

## Integration boundary
The graph now wires T2-owned nodes to implementations. T3's routing/LLM/coverage/intent/
narration implementations and T4's resolution/SQL execution/derivation/check implementations
remain adapter stubs in this ZIP and must be connected through the frozen contracts before
the graph can be called a real end-to-end agent. The CLI can exercise the graph shape, but it
does not turn those remaining stubs into production nodes.

## Setup and smoke checks
From the repository root, using Python 3.12:
1. `python -m venv .venv`
2. Activate the environment.
3. `python -m pip install -e ".[dev]"`
4. `python -m compileall -q src scripts`
5. `pytest -q`
6. `python scripts/run_agent.py --question "Show monthly rainfall in Kerala" --version v0`

The CLI's stub outcomes are for graph plumbing only and must not be reported as model
accuracy or end-to-end evaluation results.
