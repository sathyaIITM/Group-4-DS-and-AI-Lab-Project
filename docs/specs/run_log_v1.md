# Run log schema v1

The local implementation writes to `outputs/runs/runs.sqlite` (`RUN_LOG_DB` overrides the path).
Every run is written once, by `finalize_response`, in one SQLite transaction. If a write fails,
the run state is placed as JSON under `outputs/runs/failed/` and the answer is still returned.

The schema is that of design document Section 9 (`schema_version = 1`): `runs`, `node_events`,
`llm_calls`, `decisions`, `retrievals`, `sql_attempts`, `checks`, `artifacts`, `evidence`,
`data_requests`, `feedback` and `memory`; child tables are keyed by `(run_id, seq)`. `llm_calls`
carries the `LlmCallRecord` fields, including `thinking_level`, `reasoning_tokens` and
`finish_reason`. A database written by an earlier version of this module is renamed to
`runs.pre_schema_v1.sqlite`. The schema excludes API keys, IP addresses and account identifiers.

Export:
`python -m analyst.ops.export_runs --db outputs/runs/runs.sqlite --out bundles/member_YYYYMMDD-HHMM/`

The exporter writes one Parquet file per table and `manifest.json` with row counts, SHA-256
checksums, schema version and Git SHA.
