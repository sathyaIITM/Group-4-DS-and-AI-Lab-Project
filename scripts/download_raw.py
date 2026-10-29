"""Download the NFHS-5 and Mandi raw files used by scripts/preprocess_data.py.

Both resources are fetched from the data.gov.in API in CSV format, page by page,
and written to data/raw/datafile1.csv and data/raw/datafile2.csv. The API key is
read from DATA_GOV_IN_API_KEY and is never written to disk.

The Mandi resource is a rolling daily snapshot, so a new download differs from
the Milestone 2 version recorded in data/MANIFEST.md. The NCRB table
(data/raw/datafile3.csv) is not available through the API; download it from
https://www.data.gov.in/catalog/crime-india-cii-2024 (Table 1.1(ii)).

    python scripts/download_raw.py
"""

from __future__ import annotations

import csv
import io
import os
import time
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT_DIR / "data" / "raw"
API_ROOT = "https://api.data.gov.in/resource"
PAGE_SIZE = 1000
# The API stalls requests that carry httpx's default User-Agent.
HEADERS = {"User-Agent": "Mozilla/5.0 (india-analyst-agent data fetch)"}
RESOURCES = {
    "datafile1.csv": "cf80173e-fece-439d-a0b1-6e9cb510593d",  # NFHS-5 district factsheets
    "datafile2.csv": "9ef84268-d588-465a-a308-a864a43d0070",  # Mandi daily prices
}


def fetch_csv(
    client: httpx.Client, resource_id: str, key: str
) -> tuple[list[str], list[list[str]]]:
    header: list[str] = []
    rows: list[list[str]] = []
    while True:
        params = {"api-key": key, "format": "csv", "limit": PAGE_SIZE, "offset": len(rows)}
        for attempt in range(5):
            try:
                response = client.get(f"{API_ROOT}/{resource_id}", params=params)
                response.raise_for_status()
                break
            except httpx.HTTPError:
                if attempt == 4:
                    raise
                time.sleep(3)
        page = list(csv.reader(io.StringIO(response.text)))
        if len(page) < 2:
            break
        header = header or page[0]
        rows.extend(page[1:])
        if len(page) - 1 < PAGE_SIZE:
            break
    return header, rows


def main() -> None:
    key = os.environ.get("DATA_GOV_IN_API_KEY", "")
    if not key:
        raise SystemExit("DATA_GOV_IN_API_KEY is not set (see .env.example)")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers=HEADERS, timeout=90, follow_redirects=True) as client:
        for filename, resource_id in RESOURCES.items():
            header, rows = fetch_csv(client, resource_id, key)
            with (RAW_DIR / filename).open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(header)
                writer.writerows(rows)
            print(f"{filename}: {len(rows):,} rows, {len(header)} columns")


if __name__ == "__main__":
    main()
