from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from ml.preprocessing.file_integrity import sha256_file
from ml.preprocessing.normalize_nwdp_observations import normalize_nwdp_csv

NWDP_HEADERS = (
    "_id",
    "SlNo",
    "Station",
    "State LGD Code",
    "District LGD Code",
    "Latitude",
    "Longitude",
    "Data Acquisition Time",
    "RL_of_zeroGauge",
    "MeanSeaLevel",
    "River Water Level Telemetry Hourly (meter)",
)
def _write_rows(path: Path, headers: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _source_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "_id": "provider-row-001",
        "SlNo": 1,
        "Station": "Example Gauge",
        "State LGD Code": 1,
        "District LGD Code": 2,
        "Latitude": 20.25,
        "Longitude": 80.5,
        "Data Acquisition Time": "01-01-2025 05:30",
        "RL_of_zeroGauge": "",
        "MeanSeaLevel": "",
        "River Water Level Telemetry Hourly (meter)": 7.25,
    }
    row.update(overrides)
    return row


def _mapping_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Station": "Example Gauge",
        "State LGD Code": 1,
        "District LGD Code": 2,
        "Latitude": 20.25,
        "Longitude": 80.5,
        "gauge_id": "cwc-gauge-id-from-authority",
        "vertical_datum": "UNVERIFIED",
        "quality_flag": "UNVERIFIED",
        "mapping_status": "APPROVED",
        "mapping_reference": "review-ticket-001",
        "quality_mapping_reference": "qc-document-pending",
    }
    row.update(overrides)
    return row


def test_actual_nwdp_format_normalizes_without_asserting_unknown_qc_or_datum(
    tmp_path: Path,
) -> None:
    source = tmp_path / "nwdp.csv"
    mapping = tmp_path / "mapping.csv"
    output = tmp_path / "canonical_observations.csv"
    _write_rows(source, NWDP_HEADERS, [_source_row()])
    _write_rows(mapping, tuple(_mapping_row()), [_mapping_row()])

    manifest = normalize_nwdp_csv(
        source,
        mapping,
        output,
        source_timezone="Asia/Kolkata",
    )

    with output.open(encoding="utf-8", newline="") as stream:
        normalized = next(csv.DictReader(stream))
    assert normalized == {
        "gauge_id": "cwc-gauge-id-from-authority",
        "source_record_id": "provider-row-001",
        "observed_at": "2025-01-01T00:00:00Z",
        "water_level_m": "7.25",
        "vertical_datum": "UNVERIFIED",
        "quality_flag": "UNVERIFIED",
    }
    assert manifest["source_sha256"] == sha256_file(source)
    assert manifest["unresolved_quality_or_vertical_datum_rows"] == 1
    assert "does not authenticate" in manifest["evidence_boundary"]
    assert json.loads(output.with_suffix(".manifest.json").read_text(encoding="utf-8")) == manifest


def test_actual_nwdp_export_can_use_slno_when_export_omits_internal_id(tmp_path: Path) -> None:
    source = tmp_path / "nwdp.csv"
    mapping = tmp_path / "mapping.csv"
    output = tmp_path / "canonical_observations.csv"
    headers = tuple(header for header in NWDP_HEADERS if header != "_id")
    source_row = _source_row()
    del source_row["_id"]
    _write_rows(source, headers, [source_row])
    _write_rows(mapping, tuple(_mapping_row()), [_mapping_row()])

    normalize_nwdp_csv(source, mapping, output, source_timezone="Asia/Kolkata")

    with output.open(encoding="utf-8", newline="") as stream:
        assert next(csv.DictReader(stream))["source_record_id"] == "1"


def test_nwdp_site_must_match_mapping_including_coordinates(tmp_path: Path) -> None:
    source = tmp_path / "nwdp.csv"
    mapping = tmp_path / "mapping.csv"
    output = tmp_path / "canonical_observations.csv"
    _write_rows(source, NWDP_HEADERS, [_source_row()])
    _write_rows(mapping, tuple(_mapping_row()), [_mapping_row(Latitude=20.26)])

    with pytest.raises(ValueError, match="does not match an explicitly reviewed mapping"):
        normalize_nwdp_csv(source, mapping, output, source_timezone="Asia/Kolkata")


def test_nwdp_duplicate_gauge_time_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "nwdp.csv"
    mapping = tmp_path / "mapping.csv"
    output = tmp_path / "canonical_observations.csv"
    _write_rows(source, NWDP_HEADERS, [_source_row(), _source_row(_id="provider-row-002", SlNo=2)])
    _write_rows(mapping, tuple(_mapping_row()), [_mapping_row()])

    with pytest.raises(ValueError, match="duplicate gauge/time"):
        normalize_nwdp_csv(source, mapping, output, source_timezone="Asia/Kolkata")


def test_nwdp_mapping_requires_explicit_review_status(tmp_path: Path) -> None:
    source = tmp_path / "nwdp.csv"
    mapping = tmp_path / "mapping.csv"
    output = tmp_path / "canonical_observations.csv"
    _write_rows(source, NWDP_HEADERS, [_source_row()])
    _write_rows(mapping, tuple(_mapping_row()), [_mapping_row(mapping_status="PROPOSED")])

    with pytest.raises(ValueError, match="is not approved"):
        normalize_nwdp_csv(source, mapping, output, source_timezone="Asia/Kolkata")


def test_normalizer_never_overwrites_raw_source_or_mapping(tmp_path: Path) -> None:
    source = tmp_path / "nwdp.csv"
    mapping = tmp_path / "mapping.csv"
    _write_rows(source, NWDP_HEADERS, [_source_row()])
    _write_rows(mapping, tuple(_mapping_row()), [_mapping_row()])

    with pytest.raises(ValueError, match="must not overwrite the raw NWDP export"):
        normalize_nwdp_csv(source, mapping, source, source_timezone="Asia/Kolkata")
    with pytest.raises(ValueError, match="must not overwrite the raw NWDP export"):
        normalize_nwdp_csv(source, mapping, mapping, source_timezone="Asia/Kolkata")


def test_duplicate_site_mapping_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "nwdp.csv"
    mapping = tmp_path / "mapping.csv"
    output = tmp_path / "canonical_observations.csv"
    _write_rows(source, NWDP_HEADERS, [_source_row()])
    _write_rows(mapping, tuple(_mapping_row()), [_mapping_row(), _mapping_row(gauge_id="different-gauge")])

    with pytest.raises(ValueError, match="repeats an NWDP site identity"):
        normalize_nwdp_csv(source, mapping, output, source_timezone="Asia/Kolkata")
