from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .validate_emdat import validate_raw_emdat_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = PROJECT_ROOT / "ml" / "datasets" / "historical_data" / "processed"


def resolve_emdat_path() -> Path:
    """Find the raw EM-DAT workbook in either historical_data or historical_disasters."""
    candidates = [
        PROJECT_ROOT / "ml" / "datasets" / "historical_data" / "EM-DAT",
        PROJECT_ROOT / "ml" / "datasets" / "historical_disasters" / "EM-DAT",
    ]
    for base in candidates:
        if base.exists():
            xlsx_files = sorted(base.glob("*.xlsx")) + sorted(base.glob("*.xls"))
            valid = [path for path in xlsx_files if "emdat" in path.name.lower()]
            if valid:
                return valid[0]
    raise FileNotFoundError(
        "EM-DAT workbook not found. Expected a raw file under ml/datasets/historical_data/EM-DAT or ml/datasets/historical_disasters/EM-DAT."
    )


def inspect_emdat_dataset(path: str | Path | None = None) -> dict[str, Any]:
    file_path = Path(path) if path is not None else resolve_emdat_path()
    frame = pd.read_excel(file_path, sheet_name="EM-DAT Data")
    validation = validate_raw_emdat_dataset(frame)
    summary = {
        "source_file": str(file_path),
        "shape": {"rows": int(frame.shape[0]), "columns": int(frame.shape[1])},
        "column_names": list(frame.columns),
        "dtypes": {key: str(value) for key, value in frame.dtypes.items()},
        "missing_values": {
            column: round(float(percent), 3) for column, percent in (frame.isna().mean() * 100).sort_values(ascending=False).items()
        },
        "duplicate_rows": int(frame.duplicated().sum()),
        "countries": sorted(frame["Country"].dropna().unique().tolist()),
        "country_count": int(frame["Country"].nunique(dropna=True)),
        "disaster_types": sorted(frame["Disaster Type"].dropna().unique().tolist()),
        "disaster_subtypes": sorted(frame["Disaster Subtype"].dropna().unique().tolist()),
        "year_range": {
            "start": int(frame["Start Year"].dropna().min()) if frame["Start Year"].notna().any() else None,
            "end": int(frame["Start Year"].dropna().max()) if frame["Start Year"].notna().any() else None,
        },
        "coordinate_availability": {
            "latitude_present": int(frame["Latitude"].notna().sum()),
            "longitude_present": int(frame["Longitude"].notna().sum()),
            "latitude_missing_pct": round(float(frame["Latitude"].isna().mean() * 100), 3),
            "longitude_missing_pct": round(float(frame["Longitude"].isna().mean() * 100), 3),
        },
        "year_distribution": (
            frame["Start Year"].value_counts().sort_index().astype(int).to_dict()
        ),
        "validation": validation,
    }
    return summary


def main() -> None:
    report = inspect_emdat_dataset()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "emdat_inspection_report.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "source_file": report["source_file"],
        "shape": report["shape"],
        "country_count": report["country_count"],
        "disaster_types": report["disaster_types"],
        "year_range": report["year_range"],
        "duplicate_rows": report["duplicate_rows"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
