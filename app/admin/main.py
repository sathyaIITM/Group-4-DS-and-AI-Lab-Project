"""Admin service: dataset onboarding review, data requests and retraining approval.

Scaffold only.
"""

from __future__ import annotations

from fastapi import FastAPI

from analyst import __version__

app = FastAPI(title="India analyst agent — admin", version=__version__)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe used by Compose and the edge proxy."""
    return {"status": "ok", "version": __version__}
