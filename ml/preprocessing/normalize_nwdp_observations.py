from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from ml.preprocessing.file_integrity import sha256_file
from ml.preprocessing.flood_training_data_import import (
    _number,
    _parse_timestamp,
    _text,
)

NWDP_COLUMNS = (
    "Station",
    "State LGD Code",
    "District LGD Code",
    "Latitude",
    "Longitude",
    "Data Acquisition Time",
    "River Water Level Telemetry Hourly (meter)",
)
MAPPING_COLUMNS = (
    "Station",
    "State LGD Code",
    "District LGD Code",
    "Latitude",
    "Longitude",
    "gauge_id",
    "vertical_datum",
    "quality_flag",
    "mapping_status",
    "mapping_reference",
    "quality_mapping_reference",
)


def _read_rows(path: str | Path, required: tuple[str, ...], dataset: str) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"{dataset} CSV has no header.")
        missing = set(required) - set(reader.fieldnames)
        if missing:
            raise ValueError(
                f"{dataset} CSV does not match the expected NWDP source format; "
                f"missing fields: {', '.join(sorted(missing))}."
            )
        rows = list(reader)
    if not rows:
        raise ValueError(f"{dataset} CSV contains no records.")
    return rows


def _site_key(row: dict[str, Any]) -> tuple[str, str, str, float, float]:
    station = str(row.get("Station", "")).strip()
    state_code = str(row.get("State LGD Code", "")).strip()
    district_code = str(row.get("District LGD Code", "")).strip()
    if not station or not state_code or not district_code:
        raise ValueError("NWDP site identity requires station and both LGD codes.")
    latitude = _number(row.get("Latitude"), "NWDP Latitude")
    longitude = _number(row.get("Longitude"), "NWDP Longitude")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("NWDP site coordinates are outside WGS 84 bounds.")
    return (
        station.casefold(),
        state_code,
        district_code,
        latitude,
        longitude,
    )


def normalize_nwdp_csv(
    source_path: str | Path,
    mapping_path: str | Path,
    output_path: str | Path,
    *,
    source_timezone: str,
) -> dict[str, Any]:
    """Map NWDP's actual CWC water-level CSV to canonical rows without inventing QC."""
    source = Path(source_path)
    mapping_file = Path(mapping_path)
    output = Path(output_path)
    if output.resolve() in {source.resolve(), mapping_file.resolve()}:
        raise ValueError("Output path must not overwrite the raw NWDP export or site mapping.")
    source_rows = _read_rows(source, NWDP_COLUMNS, "NWDP source")
    mappings = _read_rows(mapping_file, MAPPING_COLUMNS, "reviewed gauge mapping")
    mapped_sites: dict[tuple[str, str, str, float, float], dict[str, str]] = {}
    seen_gauges: set[str] = set()
    for row in mappings:
        key = _site_key(row)
        gauge_id = _text(row, "gauge_id", "reviewed gauge mapping")
        if gauge_id in seen_gauges:
            raise ValueError(f"Gauge mapping repeats gauge_id {gauge_id!r}.")
        if key in mapped_sites:
            raise ValueError("Reviewed gauge mapping repeats an NWDP site identity.")
        seen_gauges.add(gauge_id)
        if _text(row, "mapping_status", "reviewed gauge mapping").upper() != "APPROVED":
            raise ValueError(f"NWDP site mapping for {gauge_id!r} is not approved.")
        _text(row, "mapping_reference", "reviewed gauge mapping")
        _text(row, "quality_mapping_reference", "reviewed gauge mapping")
        mapped_sites[key] = row

    canonical_rows: list[dict[str, Any]] = []
    seen_observations: set[tuple[str, str]] = set()
    source_record_ids = ("_id", "SlNo")
    for source_row in source_rows:
        key = _site_key(source_row)
        mapping = mapped_sites.get(key)
        if mapping is None:
            raise ValueError(
                "NWDP site does not match an explicitly reviewed mapping by station, LGD codes, "
                "and exact coordinates. Do not select a nearest station automatically."
            )
        source_id = next(
            (str(source_row[name]).strip() for name in source_record_ids
             if str(source_row.get(name, "")).strip()),
            "",
        )
        if not source_id:
            raise ValueError("NWDP record must contain source _id or SlNo.")
        gauge_id = _text(mapping, "gauge_id", "reviewed gauge mapping")
        observed_at = _parse_timestamp(
            source_row["Data Acquisition Time"],
            "NWDP Data Acquisition Time",
            source_timezone,
        )
        identity = (gauge_id, observed_at.isoformat())
        if identity in seen_observations:
            raise ValueError(
                f"NWDP source contains duplicate gauge/time observation for {gauge_id!r}."
            )
        seen_observations.add(identity)
        water_level = str(source_row["River Water Level Telemetry Hourly (meter)"]).strip()
        if water_level not in {"", "-", "NA", "N/A", "null", "None"}:
            _number(water_level, "NWDP river water level")
        canonical_rows.append(
            {
                "gauge_id": gauge_id,
                "source_record_id": source_id,
                "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
                "water_level_m": water_level,
                "vertical_datum": _text(mapping, "vertical_datum", "reviewed gauge mapping"),
                "quality_flag": _text(mapping, "quality_flag", "reviewed gauge mapping"),
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "gauge_id",
                "source_record_id",
                "observed_at",
                "water_level_m",
                "vertical_datum",
                "quality_flag",
            ),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(canonical_rows)
    manifest = {
        "manifest_version": "1.0",
        "normalization": "nwdp-cwc-water-level-csv-to-canonical-observations-v1",
        "source_file": str(source.resolve()),
        "source_sha256": sha256_file(source),
        "mapping_file": str(mapping_file.resolve()),
        "mapping_sha256": sha256_file(mapping_file),
        "source_timezone": source_timezone,
        "output_file": str(output.resolve()),
        "output_sha256": sha256_file(output),
        "row_count": len(canonical_rows),
        "unresolved_quality_or_vertical_datum_rows": sum(
            1
            for row in canonical_rows
            if row["quality_flag"].upper() not in {"VALID", "GOOD", "APPROVED"}
            or row["vertical_datum"].upper() in {"UNKNOWN", "UNVERIFIED", "NA", "N/A"}
        ),
        "evidence_boundary": (
            "This transforms source fields using operator-provided mappings. It does not authenticate "
            "gauge identity, QC, vertical datum, scientific review, access, or licensing."
        ),
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize an actual NWDP CWC water-level CSV using an explicit reviewed site mapping."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--site-mapping", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-timezone", required=True)
    args = parser.parse_args()
    try:
        manifest = normalize_nwdp_csv(
            args.source,
            args.site_mapping,
            args.output,
            source_timezone=args.source_timezone,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
