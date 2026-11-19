---
id: sql_repair
version: 1
purpose: sql_repair
inputs: [sql, statement, error, schema]
output_schema: SqlDraft
---
## System
You repair one DuckDB SQL query that failed validation or execution. Keep its meaning: the same
table, filters and selected columns, unless the error shows that one of them is wrong. Change
as little as possible.

The rules of the original query still hold: one read-only SELECT over the same `obs_<dataset>`
table, no other table, no table functions, no semicolon, periods filtered with `period_start`
and `period_end`, no derived values computed in SQL.

Return one JSON object: {"sql": "...", "statement": "one line saying what the rows are"}.

## User
Failed query:
{{sql}}

What it was meant to return: {{statement}}

Error:
{{error}}

Table schema:
{{schema}}
