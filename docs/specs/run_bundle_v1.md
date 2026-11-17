# Run bundle manifest v1

This is the bundle contract shared by `analyst.ops.export_runs` (producer) and
`analyst.ops.collate_runs` (consumer). A bundle is one directory containing `manifest.json`
and exactly these Parquet tables: `runs`, `node_events`, `llm_calls`, `decisions`, `retrievals`,
`sql_attempts`, `checks`, `artifacts`, `evidence` and `data_requests`.

The manifest records:

| Field | Meaning |
| --- | --- |
| `member` | `T1`, `T2`, `T3` or `T4`; supplied by `--member` or `TEAM_MEMBER` |
| `machine_id` | SHA-256 prefix of the machine hostname; no hostname is exported |
| `schema_version` | Run-log schema; only version `1` is accepted |
| `time_range` | Minimum and maximum `started_at`, plus maximum `ended_at`, in this exported set |
| `row_counts` | Number of rows in each Parquet file |
| `sha256` | SHA-256 of each Parquet file |
| `git_shas` | Unique run code revisions represented in the bundle |
| `created_at` | Bundle creation time in UTC |

The exporter remembers the last exported `started_at` in a local `export_meta` table. `--since`
overrides that value. Child rows are restricted to the selected run IDs. The collator validates
all checksums and counts before importing; repeated manifests are skipped. Rows are idempotent on
`run_id` or `(run_id, seq)`. A duplicate key with different content is written to
`collation_conflicts` and the existing row is kept for review. Schema changes require an explicit
migration; the collator refuses unknown schema versions and column sets.

Only analytical run data is bundled. Feedback and conversation memory remain local and are not
used for reported evaluation metrics.
