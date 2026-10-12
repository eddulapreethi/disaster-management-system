from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

from .inspect_emdat import resolve_emdat_path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = PROJECT_ROOT / "ml" / "datasets" / "historical_data" / "processed"


DISASTER_MAPPINGS = {
    "floods.csv": ["Flood"],
    "glacial_lake_outburst_floods.csv": ["Glacial lake outburst flood"],
    "storms_cyclones.csv": ["Storm"],
    "landslides.csv": ["Mass movement (wet)", "Mass movement (dry)"],
    "wildfires.csv": ["Wildfire"],
    "earthquakes.csv": ["Earthquake"],
}


def _write_manifest(
    output_path: Path,
    frame: pd.DataFrame,
    source_path: Path,
    raw_source_path: Path | None,
    disaster_types: list[str],
    excluded_rows: int,
) -> dict[str, object]:
    dataset_hash = hashlib.sha256(output_path.read_bytes()).hexdigest()
    raw_source = raw_source_path or source_path
    source_match = re.search(r"(20\d{2}-\d{2}-\d{2})", raw_source.name)
    start_dates = pd.to_datetime(frame.get("start_date"), errors="coerce")
    coordinates = frame.dropna(subset=["latitude", "longitude"])
    manifest = {
        "manifest_version": "1.0",
        "dataset_name": output_path.stem,
        "dataset_version": "1",
        "source_name": "EM-DAT International Disaster Database",
        "source_reference": "https://public.emdat.be/",
        "source_file": str(raw_source.name),
        "source_sha256": hashlib.sha256(raw_source.read_bytes()).hexdigest(),
        "processed_input_file": source_path.name,
        "processed_input_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "retrieval_date": None,
        "retrieval_date_note": (
            "The supplied source file does not record its actual retrieval date. "
            "A date in the filename is recorded separately and is not treated as retrieval evidence."
        ),
        "source_filename_date": source_match.group(1) if source_match else None,
        "manifest_generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "license": (
            "Subject to the access terms for the supplied EM-DAT academic/research request; "
            "this pipeline does not grant or confirm redistribution rights."
        ),
        "row_definition": "One EM-DAT event record whose source Disaster Type matches the selected category.",
        "event_categories": disaster_types,
        "target_definition": (
            "Historical event classification only. This is not a local inundation label, "
            "river threshold exceedance, or continuous flood probability."
        ),
        "geographic_coverage": {
            "countries": sorted(frame["country"].dropna().unique().tolist()),
            "event_coordinate_bounds": (
                {
                    "west": float(coordinates["longitude"].min()),
                    "south": float(coordinates["latitude"].min()),
                    "east": float(coordinates["longitude"].max()),
                    "north": float(coordinates["latitude"].max()),
                }
                if not coordinates.empty
                else None
            ),
            "rows_with_both_coordinates": int(len(coordinates)),
        },
        "temporal_coverage": {
            "start": str(start_dates.min().date()) if start_dates.notna().any() else None,
            "end": str(start_dates.max().date()) if start_dates.notna().any() else None,
        },
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "dataset_sha256": dataset_hash,
        "columns": [
            {
                "name": column,
                "definition": "Preserved from cleaned EM-DAT source fields; see the source data dictionary.",
                "unit": "Source-defined; consult the source workbook and data dictionary.",
            }
            for column in frame.columns
        ],
        "missing_values": {column: int(count) for column, count in frame.isna().sum().items()},
        "excluded_rows": {
            "count": excluded_rows,
            "reason": "Rows with other disaster_type values are excluded from this category-specific output.",
        },
        "validation": {
            "non_empty": not frame.empty,
            "unique_disaster_ids": bool(frame["disno."].is_unique) if "disno." in frame else None,
            "sha256": dataset_hash,
            "training_suitable": False,
            "training_blocker": (
                "No matched environmental observation table, verified site-level target, "
                "or documented model feature mapping."
            ),
        },
        "processing_version": "emdat-category-filter-v2",
    }
    output_path.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def generate_disaster_specific_datasets(cleaned_csv: str | Path | None = None, output_dir: str | Path | None = None) -> dict[str, pd.DataFrame]:
    source = Path(cleaned_csv) if cleaned_csv else PROCESSED_DIR / "emdat_cleaned.csv"
    destination = Path(output_dir) if output_dir else PROCESSED_DIR
    destination.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(source)
    try:
        raw_source = resolve_emdat_path()
    except FileNotFoundError:
        raw_source = None
    results: dict[str, pd.DataFrame] = {}
    for file_name, disaster_types in DISASTER_MAPPINGS.items():
        subset = frame[frame["disaster_type"].isin(disaster_types)].copy()
        if subset.empty:
            subset = frame.iloc[0:0].copy()
        subset = subset.sort_values(["start_year", "country"], ascending=[True, True]).reset_index(drop=True)
        output_path = destination / file_name
        subset.to_csv(output_path, index=False, lineterminator="\n")
        _write_manifest(
            output_path,
            subset,
            source,
            raw_source,
            disaster_types,
            excluded_rows=int((~frame["disaster_type"].isin(disaster_types)).sum()),
        )
        results[file_name] = subset
    return results


def main() -> None:
    results = generate_disaster_specific_datasets()
    print({name: int(frame.shape[0]) for name, frame in results.items()})


if __name__ == "__main__":
    main()
