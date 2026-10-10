from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from .inspect_emdat import resolve_emdat_path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = PROJECT_ROOT / "ml" / "datasets" / "historical_data" / "processed"


def normalize_column_name(name: str) -> str:
    cleaned = str(name).strip()
    cleaned = cleaned.replace("(", " ").replace(")", " ")
    cleaned = cleaned.replace("/", " ").replace("-", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.lower().replace(" ", "_")
    cleaned = cleaned.replace("_000_us_", "_000_us_")
    return cleaned


def _build_date_from_parts(row: pd.Series, year_column: str, month_column: str, day_column: str) -> pd.Timestamp | pd.NaT:
    year = pd.to_numeric(row[year_column], errors="coerce")
    if pd.isna(year):
        return pd.NaT

    month = pd.to_numeric(row[month_column], errors="coerce")
    day = pd.to_numeric(row[day_column], errors="coerce")
    if pd.isna(month) or pd.isna(day):
        return pd.NaT

    date_string = f"{int(year):d}-{int(month):02d}-{int(day):02d}"
    return pd.to_datetime(date_string, errors="coerce")


def build_cleaned_frame(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned = frame.copy()
    cleaned.columns = [normalize_column_name(column) for column in cleaned.columns]
    numeric_year_columns = ["start_year", "end_year", "start_month", "start_day", "end_month", "end_day"]
    for column in numeric_year_columns:
        if column in cleaned.columns:
            cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    for column in ["latitude", "longitude"]:
        if column in cleaned.columns:
            cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    for column in [
        "total_deaths",
        "no_injured",
        "no_affected",
        "no_homeless",
        "total_affected",
        "magnitude",
        "cpi",
        "aid_contribution_000_us",
        "reconstruction_costs_000_us",
        "reconstruction_costs_adjusted_000_us",
        "insured_damage_000_us",
        "insured_damage_adjusted_000_us",
        "total_damage_000_us",
        "total_damage_adjusted_000_us",
    ]:
        if column in cleaned.columns:
            cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    cleaned["start_date"] = cleaned.apply(
        lambda row: _build_date_from_parts(row, "start_year", "start_month", "start_day"),
        axis=1,
    )
    cleaned["end_date"] = cleaned.apply(
        lambda row: _build_date_from_parts(row, "end_year", "end_month", "end_day"),
        axis=1,
    )
    cleaned["event_date"] = cleaned["start_date"]
    cleaned["country"] = cleaned["country"].replace({"": pd.NA})
    cleaned["disaster_type"] = cleaned["disaster_type"].replace({"": pd.NA})
    cleaned["disaster_subtype"] = cleaned["disaster_subtype"].replace({"": pd.NA})
    return cleaned


def clean_emdat_dataset(input_path: str | Path | None = None, output_path: str | Path | None = None) -> pd.DataFrame:
    raw_path = Path(input_path) if input_path else resolve_emdat_path()
    frame = pd.read_excel(raw_path, sheet_name="EM-DAT Data")
    cleaned = build_cleaned_frame(frame)
    output = Path(output_path) if output_path else PROCESSED_DIR / "emdat_cleaned.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(output, index=False)
    return cleaned


def main() -> None:
    frame = clean_emdat_dataset()
    print({
        "rows": int(frame.shape[0]),
        "columns": int(frame.shape[1]),
        "source": str(resolve_emdat_path()),
        "output": str(PROCESSED_DIR / "emdat_cleaned.csv"),
    })


if __name__ == "__main__":
    main()
