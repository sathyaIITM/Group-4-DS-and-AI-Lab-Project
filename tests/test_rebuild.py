"""Rebuild equality: the configured pipeline must reproduce the Milestone 2 tables.

The golden files are the Milestone 2 outputs (their checksums are asserted below). The
agent-facing tables rebuilt from configuration must hold the same values, apart from
(a) the new quality columns, (b) the shared flag vocabulary and (c) five place-name
spellings that the reference table now standardises. The 90 executable reference
queries must return the same results. The tests need the downloaded raw files and are
skipped without them.
"""

import hashlib
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from analyst.data import publish
from analyst.data.config import load_all
from analyst.data.source_rules import RULES

RAW = Path("data/raw")
GOLDEN = Path("data/processed/golden_v1")
pytestmark = pytest.mark.skipif(
    not (RAW / "datafile1.csv").exists() or not GOLDEN.exists(),
    reason="needs the downloaded raw files and the Milestone 2 golden outputs",
)

# SHA-256 of the Milestone 2 outputs, as recorded in the submitted data manifest.
GOLDEN_SHA256 = {
    "imd_subdivision_monthly_rainfall": "9db782cb7ef9af0b48c3e2e5b3ef63f106c28ee2782c919e261f008f1fb02891",  # noqa: E501
    "mandi_daily_prices": "74fccb849339cd9592ccf882c148ab0080f380415123d0b26c15120ed1aebd8e",
    "ncrb_annual_crime_statistics": "e4878fad6dbc66a01e079d5ccd552f8b48b2c3880772249e72d7539af0364f6b",  # noqa: E501
    "nfhs5_district_indicators": "8308c32c297eafa03dd9ef8129e6a3a97a86d81b5cd88fb6df195af0eda73731",
    "plfs_state_ur_usual_status": "02294673edc08311080cac3c3ead40fc4609a6e0b0d2c71a0847bc77b66f6dab",  # noqa: E501
}
# Old flag name -> shared vocabulary (a rename; no value changes meaning).
FLAG_RENAME = {
    "missing_or_unparseable": "unparsed",
    "invalid_arrival_date": "unparsed",
    "negative_or_missing_price": "out_of_range",
    "invalid_price_order": "inconsistent",
    "implausible_price": "implausible",
    "passed": "reported",
    "negative_values": "out_of_range",
    "duplicate_year": "inconsistent",
    "validation_failed": "inconsistent",
}
# Place names the old hard-coded list left unstandardised; the alias table now maps them.
STATE_CORRECTIONS = {
    "Dadra and Nagar Haveli & Daman and Diu": "Dadra and Nagar Haveli and Daman and Diu",
    "Jammu & Kashmir": "Jammu and Kashmir",
    "Maharastra": "Maharashtra",
    "Andaman and Nicobar": "Andaman and Nicobar Islands",
    "Chattisgarh": "Chhattisgarh",
}
# Reference queries whose flag filter was renamed with the vocabulary.
LEGACY_SQL = {
    "quality_flag IN ('missing_in_source', 'unparsed')": "quality_flag = 'missing_or_unparseable'",
    "quality_flag='inconsistent'": "quality_flag='invalid_price_order'",
}


@pytest.fixture(scope="module")
def release(tmp_path_factory: pytest.TempPathFactory):
    out = tmp_path_factory.mktemp("processed")
    results, entries = {}, []
    for config in load_all():
        result = publish.run_with_baseline(config, RAW)
        assert not result.blocked, [i for i in result.review if i.severity == "block"]
        entries.append(publish.publish(result, out_dir=out, lineage_dir=out / "lineage"))
        results[config.dataset_id] = result
    publish.update_catalogue(entries, out)
    return out, results


def _canonical(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    frame = frame[columns].copy()
    for column in columns:
        series = frame[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            frame[column] = pd.to_datetime(series).dt.strftime("%Y-%m-%d")
        elif pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
            frame[column] = pd.to_numeric(series, errors="coerce").astype("float64").round(9)
        elif pd.api.types.is_bool_dtype(series) or str(series.dtype) == "boolean":
            frame[column] = series.astype("object").map(lambda x: None if pd.isna(x) else bool(x))
        else:
            frame[column] = series.astype("object").where(series.notna(), None)
    return frame.sort_values(columns, key=lambda s: s.astype(str), kind="stable").reset_index(
        drop=True
    )


@pytest.mark.parametrize("dataset_id", sorted(GOLDEN_SHA256))
def test_golden_files_are_the_submitted_milestone_2_outputs(dataset_id: str) -> None:
    digest = hashlib.sha256((GOLDEN / f"{dataset_id}.parquet").read_bytes()).hexdigest()
    assert digest == GOLDEN_SHA256[dataset_id]


@pytest.mark.parametrize("dataset_id", sorted(GOLDEN_SHA256))
def test_agent_table_holds_the_same_values_as_milestone_2(release, dataset_id: str) -> None:
    out, _ = release
    old = pd.read_parquet(GOLDEN / f"{dataset_id}.parquet")
    new = pd.read_parquet(out / f"{dataset_id}.parquet")
    assert set(old.columns) <= set(new.columns)  # nothing dropped; only columns added
    if "quality_flag" in old:
        old["quality_flag"] = old["quality_flag"].map(lambda f: FLAG_RENAME.get(f, f))
    if "state_name" in old:
        old["state_name"] = old["state_name"].map(lambda s: STATE_CORRECTIONS.get(s, s))
    columns = list(old.columns)
    assert len(old) == len(new)
    left, right = _canonical(old, columns), _canonical(new, columns)
    different = [c for c in columns if not left[c].equals(right[c])]
    assert different == []


def test_only_five_place_names_changed_and_all_are_listed(release) -> None:
    out, _ = release
    changed: dict[str, str] = {}
    for dataset_id in ("nfhs5_district_indicators", "mandi_daily_prices"):
        old = pd.read_parquet(GOLDEN / f"{dataset_id}.parquet", columns=["state_name"])
        new = pd.read_parquet(out / f"{dataset_id}.parquet", columns=["state_name"])
        for before, after in zip(old["state_name"], new["state_name"], strict=True):
            if before != after:
                changed[before] = after
    assert changed == STATE_CORRECTIONS


def test_new_observation_tables_carry_a_flag_and_raw_text_on_every_value(release) -> None:
    out, results = release
    for dataset_id, result in results.items():
        obs = pd.read_parquet(out / f"obs_{dataset_id}.parquet")
        assert obs["quality_flag"].notna().all() and obs["unit"].notna().all()
        assert (
            obs["value"].isna()
            == obs["quality_flag"].isin(["unparsed", "missing_in_source", "suppressed"])
        ).all()
        assert len(obs) == result.lineage["observations"]


def test_milestone_2_flag_counts_are_reproduced(release) -> None:
    _, results = release
    flags = {k: r.lineage["flag_counts"] for k, r in results.items()}
    assert flags["nfhs5_district_indicators"]["suppressed"] == 4132
    assert flags["nfhs5_district_indicators"]["low_sample_estimate"] == 4884
    assert flags["imd_subdivision_monthly_rainfall"]["missing_in_source"] == 134
    assert flags["plfs_state_ur_usual_status"]["missing_in_source"] == 4
    assert flags["mandi_daily_prices"].get("implausible", 0) > 0
    assert set(flags["ncrb_annual_crime_statistics"]) == {"reported"}


def test_source_rule_changed_exactly_the_number_of_values_it_documents(release) -> None:
    _, results = release
    touched = results["nfhs5_district_indicators"].lineage["values_touched_by_rule"]
    assert (
        touched["nfhs5_minus_as_low_sample"] == RULES["nfhs5_minus_as_low_sample"].observed_values
    )
    obs = results["nfhs5_district_indicators"].obs
    assert (obs["value"].dropna() >= 0).all()  # no negative value remains


def test_reference_queries_return_the_same_results(release) -> None:
    out, _ = release
    tables = [c.view.table for c in load_all()]

    def connect(base: Path) -> duckdb.DuckDBPyConnection:
        con = duckdb.connect()
        for table in tables:
            con.execute(
                f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{base / table}.parquet')"  # noqa: S608
            )
        return con

    def rows(con: duckdb.DuckDBPyConnection, sql: str, fix: bool) -> list[tuple]:
        fetched = con.execute(sql).fetchall()
        if fix:
            fetched = [
                tuple(STATE_CORRECTIONS.get(x, x) if isinstance(x, str) else x for x in r)
                for r in fetched
            ]
        return sorted(
            (tuple(round(x, 6) if isinstance(x, float) else x for x in r) for r in fetched),
            key=repr,
        )

    reference = pd.read_csv("data/ground_truths/text_to_sql_ground_truth_100.csv").dropna(
        subset=["gold_sql"]
    )
    old, new = connect(GOLDEN), connect(out)
    different = []
    for _, question in reference.iterrows():
        legacy = question.gold_sql
        for current, previous in LEGACY_SQL.items():
            legacy = legacy.replace(current, previous)
        if rows(old, legacy, True) != rows(new, question.gold_sql, False):
            different.append(question.id)
    assert len(reference) == 90
    assert different == []


def test_catalogue_is_recomputed_from_the_published_data(release) -> None:
    out, _ = release
    assert publish.verify_release(out_dir=out) == []


def test_catalogue_detects_a_fact_that_was_typed_by_hand(release) -> None:
    import json
    import shutil

    out, _ = release
    copy = out.parent / "tampered"
    shutil.copytree(out, copy)
    document = json.loads((copy / "catalogue.json").read_text())
    document["tables"][0]["coverage_end"] = "2099-12-31"
    (copy / "catalogue.json").write_text(json.dumps(document))
    assert any("coverage_end" in p for p in publish.verify_release(out_dir=copy))
