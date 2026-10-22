# Tests

`pytest` from the repository root. Layout mirrors `src/analyst`.

Markers: `slow`, `needs_gpu`, `needs_api`. The default run excludes nothing, so
select explicitly in constrained environments, for example
`pytest -m "not needs_api and not needs_gpu"`.

Tests must not download data or call a paid API unless marked `needs_api`. Use
the extracts in `data/sample` instead.
