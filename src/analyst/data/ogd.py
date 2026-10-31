"""Download resources from the Open Government Data Platform India (data.gov.in).

The API returns JSON pages. The key is read from the DATA_GOV_IN_API_KEY
environment variable and is never written to disk or logged.
"""

import os
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

API_ROOT = "https://api.data.gov.in/resource"
PAGE_SIZE = 1000
TIMEOUT_S = 60.0
# The API stalls requests that carry httpx's default User-Agent.
HEADERS = {"User-Agent": "Mozilla/5.0 (india-analyst-agent data fetch)"}


def _api_key() -> str:
    key = os.environ.get("DATA_GOV_IN_API_KEY", "")
    if not key:
        msg = "DATA_GOV_IN_API_KEY is not set (see .env.example)"
        raise RuntimeError(msg)
    return key


def fetch_resource(
    resource_id: str, max_rows: int | None = None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fetch every record of a resource.

    Returns the records as a DataFrame and the resource metadata (title, total,
    field list, update dates) taken from the first page.
    """
    key = _api_key()
    records: list[dict[str, Any]] = []
    meta: dict[str, Any] = {}
    offset = 0
    with httpx.Client(timeout=TIMEOUT_S, follow_redirects=True, headers=HEADERS) as client:
        while True:
            response = client.get(
                f"{API_ROOT}/{resource_id}",
                params={
                    "api-key": key,
                    "format": "json",
                    "offset": offset,
                    "limit": PAGE_SIZE,
                },
            )
            response.raise_for_status()
            page = response.json()
            if not meta:
                meta = {k: v for k, v in page.items() if k not in {"records", "api-key"}}
            batch = page.get("records", [])
            records.extend(batch)
            offset += len(batch)
            total = int(page.get("total", 0))
            if not batch or offset >= total or (max_rows is not None and offset >= max_rows):
                break
    frame = pd.DataFrame.from_records(records)
    if max_rows is not None:
        frame = frame.head(max_rows)
    return frame, meta


def save_raw(frame: pd.DataFrame, name: str, raw_dir: Path) -> Path:
    """Write a fetched resource unchanged to data/raw as CSV."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{name}.csv"
    frame.to_csv(path, index=False)
    return path
