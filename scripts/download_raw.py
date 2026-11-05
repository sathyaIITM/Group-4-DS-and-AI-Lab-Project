"""Download raw files from the data.gov.in API into data/raw.

Each resource in RESOURCES is fetched in CSV format, page by page, and written to
data/raw/<file name>. The API key is read from DATA_GOV_IN_API_KEY and is never
written to disk. Names given on the command line restrict the download to those
files; with no names, every resource is downloaded.

The Mandi resource is a rolling daily snapshot, so a new download differs from
the Milestone 2 version recorded in data/MANIFEST.md. The NCRB table
(data/raw/datafile3.csv) is not available through the API; download it from
https://www.data.gov.in/catalog/crime-india-cii-2024 (Table 1.1(ii)). The source
of each T1 table is recorded in docs/specs/candidate_tables.md.

    python scripts/download_raw.py
    python scripts/download_raw.py cpi_all_india.csv msp_crops.csv
"""

from __future__ import annotations

import csv
import io
import os
import sys
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
    # T1 tables (docs/specs/candidate_tables.md)
    "crop_production_district.csv": "35be999b-0208-4354-b557-f6ca9a5355de",  # T1-1
    "cpi_all_india.csv": "2a6edbfb-b416-48db-9183-645be023f757",  # T1-2
    "cpi_state.csv": "09a191c9-3b2a-44ac-8d25-02475f83e723",  # T1-3
    "nfhs5_state_factsheet.csv": "7c568619-b9b4-40bb-b563-68c28c27a6c1",  # T1-4
    "imd_district_rainfall_normals.csv": "d0419b03-b41b-4226-b48b-0bc92bf139f8",  # T1-5
    "census2011_pca.csv": "0764657f-00ec-4c6b-9ece-2d7b8a7401fa",  # T1-6
    "plfs_lfpr_urban_state.csv": "67634139-cc72-4f90-a82f-d2b9b22488dc",  # T1-7
    "srs_imr_state.csv": "d64574ca-33b9-4108-bd90-b3de1edd82a8",  # T2-1
    "gsdp_per_capita_state.csv": "af17f25b-3bdf-4eeb-b3e3-b0fc93df16a7",  # T2-2
    "msp_crops.csv": "82e89d31-2208-4be0-babd-2286a4d9110b",  # T2-3
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


def main(names: list[str]) -> None:
    unknown = sorted(set(names) - set(RESOURCES))
    if unknown:
        raise SystemExit(f"unknown file name(s): {', '.join(unknown)}; see RESOURCES")
    selected = {name: RESOURCES[name] for name in names} if names else RESOURCES
    key = os.environ.get("DATA_GOV_IN_API_KEY", "")
    if not key:
        raise SystemExit("DATA_GOV_IN_API_KEY is not set (see .env.example)")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers=HEADERS, timeout=90, follow_redirects=True) as client:
        for filename, resource_id in selected.items():
            header, rows = fetch_csv(client, resource_id, key)
            with (RAW_DIR / filename).open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(header)
                writer.writerows(rows)
            print(f"{filename}: {len(rows):,} rows, {len(header)} columns")


if __name__ == "__main__":
    main(sys.argv[1:])
