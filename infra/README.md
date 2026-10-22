# Infrastructure

| Component | Where it runs |
| --- | --- |
| `ui`, `api` (API and agent), `admin`, Postgres with pgvector, Caddy | Docker Compose on one Compute Engine VM (e2-standard-2 or e2-medium) |
| Kev | A GPU endpoint for demonstrations and reviews only (Jarvislabs L4, or Cloud Run L4 after a trial-account test). Accuracy and calibration are measured on the MacBook or CPU |
| Jev | Hosted: TypeSafe AI directly, with OpenRouter as the second backend |
| Tracing | Langfuse Cloud, free plan |

The plan does not depend on Google Cloud GPUs; the trial account cannot attach
GPUs to VMs.

## Local run

```bash
cp .env.example .env   # fill in POSTGRES_PASSWORD and any keys needed
docker compose up --build
```

The stack is then reachable at `http://localhost`: the UI at `/`, the API at
`/api` and the admin service at `/admin`. `/api/stream` is excluded from proxy
buffering so that server-sent events arrive as they are produced.

## Serving Kev locally

Kev is not part of the Compose stack. Serve it separately, per its README:

```bash
uv sync --extra serve
KEV_API_KEY=... KEV_TEMPERATURE=1.0 KEV_DTYPE=fp32 \
  uv run --extra serve python -m kev.serve \
  --run jaredpalmer/kev-0.8b --port 8009 --device auto
```

Point `KEV_BASE_URL` at that port. `KEV_TEMPERATURE=1.0` returns raw
probabilities, which the calibration fits require. Python 3.12 or 3.13 and `uv`
are required. Verify these commands against the Kev README before relying on
them.

Keep runs on the MacBook short and sequential: it is fanless with 16 GB, and
Kev-4B needs about 8.4 GB in bf16.

## Budget

Estimate to 21 December 2026: about USD 65–170, of which USD 41–83 is eligible
against the USD 300 Google Cloud credit and USD 22–88 is paid to API and GPU
providers. Estimates only. Ask the team before spending money or creating
accounts.
