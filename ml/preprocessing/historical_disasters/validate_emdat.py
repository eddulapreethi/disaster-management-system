from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = [
    "DisNo.",
    "Disaster Type",
    "Country",
    "Start Year",
    "Start Month",
    "Start Day",
    "End Year",
    "End Month",
    "End Day",
    "Latitude",
    "Longitude",
]


def validate_raw_emdat_dataset(frame: pd.DataFrame) -> dict[str, Any]:
    """Return a report of raw-data issues without mutating the original workbook."""
    issues: dict[str, Any] = {
        "duplicate_records": [],
        "missing_disaster_type": [],
        "missing_country": [],
        "invalid_years": [],
        "invalid_coordinates": [],
        "impossible_date_relationships": [],
        "invalid_numeric_values": [],
        "inconsistent_type_subtype": [],
    }
    if frame.empty:
        raise ValueError("EM-DAT dataset is empty.")
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Required EM-DAT columns are missing: {missing}")

    duplicate_rows = frame[frame.duplicated(subset=["DisNo."])].copy()
    if not duplicate_rows.empty:
        issues["duplicate_records"] = duplicate_rows["DisNo."].dropna().tolist()

    missing_type = frame.loc[frame["Disaster Type"].isna(), ["DisNo.", "Country"]].to_dict("records")
    issues["missing_disaster_type"] = missing_type

    missing_country = frame.loc[frame["Country"].isna(), ["DisNo."]].to_dict("records")
    issues["missing_country"] = missing_country

    years = pd.to_numeric(frame["Start Year"], errors="coerce")
    invalid_years = frame.loc[(years < 1900) | (years > 2100), ["DisNo.", "Start Year"]].to_dict("records")
    issues["invalid_years"] = invalid_years

    lat = pd.to_numeric(frame["Latitude"], errors="coerce")
    lon = pd.to_numeric(frame["Longitude"], errors="coerce")
    invalid_coordinates = frame.loc[
        ((lat < -90) | (lat > 90) | (lon < -180) | (lon > 180))
        & (frame["Latitude"].notna() | frame["Longitude"].notna()),
        ["DisNo.", "Latitude", "Longitude"],
    ].to_dict("records")
    issues["invalid_coordinates"] = invalid_coordinates

    start_year = pd.to_numeric(frame["Start Year"], errors="coerce")
    end_year = pd.to_numeric(frame["End Year"], errors="coerce")
    start_month = pd.to_numeric(frame["Start Month"], errors="coerce")
    end_month = pd.to_numeric(frame["End Month"], errors="coerce")
    start_day = pd.to_numeric(frame["Start Day"], errors="coerce")
    end_day = pd.to_numeric(frame["End Day"], errors="coerce")
    impossible = frame.loc[
        (
            (end_year.notna())
            & (start_year.notna())
            & ((end_year < start_year) | ((end_year == start_year) & (end_month.notna()) & (start_month.notna()) & ((end_month < start_month) | ((end_month == start_month) & (end_day.notna()) & (start_day.notna()) & (end_day < start_day)))) )
        )
        | (
            (start_year.notna())
            & (start_year > 2100)
        )
        | (
            (end_year.notna())
            & (end_year > 2100)
        ),
        ["DisNo.", "Start Year", "Start Month", "Start Day", "End Year", "End Month", "End Day"],
    ].to_dict("records")
    issues["impossible_date_relationships"] = impossible

    numeric_columns = [
        "Total Deaths",
        "No. Injured",
        "No. Affected",
        "No. Homeless",
        "Total Affected",
        "Magnitude",
        "CPI",
        "AID Contribution ('000 US$)",
        "Reconstruction Costs ('000 US$)",
        "Reconstruction Costs, Adjusted ('000 US$)",
        "Insured Damage ('000 US$)",
        "Insured Damage, Adjusted ('000 US$)",
        "Total Damage ('000 US$)",
        "Total Damage, Adjusted ('000 US$)",
    ]
    for column in numeric_columns:
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        invalid = frame.loc[(values < 0) & values.notna(), ["DisNo.", column]].to_dict("records")
        if invalid:
            issues["invalid_numeric_values"].extend([{"column": column, **row} for row in invalid])

    type_subtype = frame[["Disaster Type", "Disaster Subtype"]].copy()
    type_subtype = type_subtype.dropna(subset=["Disaster Type"])
    invalid_pairs = type_subtype.loc[
        (type_subtype["Disaster Type"].isin(["Flood", "Storm", "Mass movement (wet)", "Mass movement (dry)", "Wildfire", "Earthquake"]))
        & (type_subtype["Disaster Subtype"].isna()),
    ]
    if not invalid_pairs.empty:
        issues["inconsistent_type_subtype"] = invalid_pairs.reset_index().to_dict("records")

    return {key: value for key, value in issues.items() if value}


def validate_emdat_records(frame: pd.DataFrame) -> list[str]:
    """Return human-readable validation warnings for subsequent cleaning steps."""
    issues = validate_raw_emdat_dataset(frame)
    messages: list[str] = []
    for section, entries in issues.items():
        if not entries:
            continue
        if section == "duplicate_records":
            messages.append(f"Duplicate records found: {len(entries)}")
        elif section == "missing_disaster_type":
            messages.append(f"Missing disaster type values: {len(entries)}")
        elif section == "missing_country":
            messages.append(f"Missing country values: {len(entries)}")
        elif section == "invalid_years":
            messages.append(f"Invalid start-year values: {len(entries)}")
        elif section == "invalid_coordinates":
            messages.append(f"Out-of-range coordinates: {len(entries)}")
        elif section == "impossible_date_relationships":
            messages.append(f"Impossible date relationships: {len(entries)}")
        elif section == "invalid_numeric_values":
            messages.append(f"Negative numeric impact values: {len(entries)}")
        elif section == "inconsistent_type_subtype":
            messages.append(f"Type/subtype mismatches: {len(entries)}")
    return messages
