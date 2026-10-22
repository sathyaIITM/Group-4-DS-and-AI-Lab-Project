# Data

Large files are not tracked. `data/raw`, `data/processed` and `data/splits` are
ignored; reproduce them with the download and cleaning scripts in
`src/analyst/data` and the pipelines in `src/analyst/pipelines`.

| Directory | Contents | Tracked |
| --- | --- | --- |
| `raw/` | Unmodified downloads from data.gov.in, MoSPI, RBI, IMD, the agriculture ministry, NFHS and Census, with the retrieval date and source URL recorded alongside | No |
| `processed/` | Cleaned, versioned Parquet tables that DuckDB reads read-only | No |
| `sample/` | Small extracts committed so that tests and reviews run without downloads | Yes |
| `splits/` | The frozen 200-question test set, the 150-question dev set and the training splits | No |

The frozen test set is never used for training or tuning. Splits are separated
by question template and table, and leakage checks are run before use.

The 8–12 core tables are not yet chosen. Profiling the candidates and freezing
the list is the first Milestone 2 deliverable.
