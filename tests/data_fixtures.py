"""Small synthetic raw tables with the real headers of each configured source.

They let the pipeline be tested on a clean clone, without the downloaded raw files.
"""

import pandas as pd

from analyst.data.config import SourceConfig, load_source_config
from analyst.data.engine import RunResult, run_source
from analyst.data.ops import clean_header

IMD_VALUES = [
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "annual", "jf", "mam", "jjas", "ond",
]  # fmt: skip


def config(dataset_id: str) -> SourceConfig:
    return load_source_config(__import__("pathlib").Path(f"configs/sources/{dataset_id}.toml"))


def plfs() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sl__no_": ["1", "2", "3", "4"],
            "states_uts": ["Kerala", "Orissa", "Goa", "All India"],
            "_2017_18": ["9.4", "7.1", "13.9", "5.8"],
            "_2018_19": ["9.0", "NA", "8.7", "5.8"],
        }
    )


def imd() -> pd.DataFrame:
    rows = []
    for subdivision in ("Kerala", "Orissa"):
        for year in (1950, 1951):
            values = [str(10 + i) for i in range(len(IMD_VALUES))]
            rows.append([subdivision, str(year), *values])
    frame = pd.DataFrame(rows, columns=["subdivision", "year", *IMD_VALUES])
    frame.loc[0, "feb"] = "NA"
    return frame


def mandi() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "State": ["Odisha", "Keralam", "Kerala", "Odisha"],
            "District": ["Khordha", "Kozhikode", "Kozhikode", "Khordha"],
            "Market": ["Bhubaneswar", "Kozhikode", "Kozhikode", "Bhubaneswar"],
            "Commodity": ["Tomato", "Tomato", "Onion", "Onion"],
            "Variety": ["Local", "Local", "Big", "Big"],
            "Grade": ["FAQ", "FAQ", "FAQ", "FAQ"],
            "Arrival_Date": ["29/10/2026"] * 4,
            "Min_x0020_Price": ["2000", "2500", "1800", "1900"],
            "Max_x0020_Price": ["2400", "3000", "2200", "2300"],
            "Modal_x0020_Price": ["2200", "2800", "2000", "2100"],
        }
    )


def ncrb() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Year": ["2022"],
            "Mid-Year Projected Population (in Lakhs)": ["13797.5"],
            "Crime Incidence - IPC/BNS": ["3561379"],
            "Crime Incidence - SLL": ["2263567"],
            "Crime Incidence - Total": ["5824946"],
            "Crime Rate - IPC/BNS": ["258.1"],
            "Crime Rate - SLL": ["164.1"],
            "Crime Rate - Total": ["422.2"],
            "Percentage of IPC/BNS Crimes to Total Cognizable Crimes": ["61.1"],
        }
    )


def nfhs() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "District Names": ["Khordha", "Puri", "Nuh"],
            "State/UT": ["Odisha", "Orissa", "Haryana"],
            "Number of Households surveyed": ["600", "1,100", "650"],
            "Number of Women age 15-49 years interviewed": ["700", "800", "900"],
            "Number of Men age 15-54 years interviewed": ["100", "110", "120"],
            "Households using clean fuel for cooking3 (%)": ["74.3", "(29.5)", "-18.2"],
            "Sex ratio of the total population (females per 1,000 males)": ["1,020", "*", "930"],
            "Out of pocket expenditure per delivery in a public health facility (Rs.)": [
                "3,500", "-10557", "2,100",
            ],
        }
    )  # fmt: skip


BUILDERS = {
    "plfs_state_ur_usual_status": plfs,
    "imd_subdivision_monthly_rainfall": imd,
    "mandi_daily_prices": mandi,
    "ncrb_annual_crime_statistics": ncrb,
    "nfhs5_district_indicators": nfhs,
}


def approved(frame: pd.DataFrame) -> list[str]:
    """The header snapshot a reviewer would have approved for this frame."""
    return [clean_header(column) for column in frame.columns]


def run(dataset_id: str, frame: pd.DataFrame, approved_columns: list[str] | None) -> RunResult:
    from pathlib import Path

    return run_source(
        config(dataset_id), Path("data/raw"), raw_frame=frame, approved_columns=approved_columns
    )


def config_from_toml(text: str) -> SourceConfig:
    """A configuration written inline, for tests of features the five sources do not use."""
    import tomllib

    return SourceConfig.model_validate(tomllib.loads(text))


def edited(dataset_id: str, **sections: dict[str, object]) -> SourceConfig:
    """A copy of a source configuration with fields of some sections replaced."""
    base = config(dataset_id).model_dump(by_alias=True)
    for name, fields in sections.items():
        base[name] = {**base[name], **fields}
    return SourceConfig.model_validate(base)


def run_config(
    cfg: SourceConfig, frame: pd.DataFrame, approved_columns: list[str] | None = None
) -> RunResult:
    from pathlib import Path

    return run_source(cfg, Path("data/raw"), raw_frame=frame, approved_columns=approved_columns)
