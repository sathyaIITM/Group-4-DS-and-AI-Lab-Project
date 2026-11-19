"""Admin service: dataset onboarding review, data requests and retraining approval.

Only the health check is implemented; the review and approval screens are planned.
"""

from __future__ import annotations

from fastapi import FastAPI

from analyst import __version__

app = FastAPI(title="India analyst agent: admin", version=__version__)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe used by Compose and the edge proxy."""
    return {"status": "ok", "version": __version__}
