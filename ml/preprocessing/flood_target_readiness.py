from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from ml.preprocessing.flood_environmental_dataset import (
    TARGET_DEFINITION,
    TARGET_DEFINITION_STATUS,
    TARGET_ID,
    build_predictor_frame,
)
from ml.preprocessing.file_integrity import sha256_file

UNKNOWN_DATUMS = {"", "UNKNOWN", "UNVERIFIED", "NA", "N/A"}


def _csv_rows(
    path: Path,
    required_columns: tuple[str, ...] = (),
) -> tuple[list[dict[str, str]], str | None]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames:
                return [], "CSV has no header"
            missing = set(required_columns) - set(reader.fieldnames)
            if missing:
                return [], f"CSV is missing columns: {', '.join(sorted(missing))}"
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as error:
        return [], str(error)
    if not rows:
        return [], "CSV has no records"
    return rows, None


def _requirement(status: str, path: str | None, details: str) -> dict[str, Any]:
    return {
        "status": status,
        "path": path,
        "details": details,
        "syntax_status": "NOT_CHECKED",
        "source_verification_status": "NOT_VERIFIED",
        "scientific_review_status": "NOT_REVIEWED",
    }


def get_flood_target_readiness(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    data_root = root / "ml" / "datasets"
    evidence = {
        "approved_target_review": data_root / "flood_training" / "target_approval.json",
        "historical_gauge_observations": (
            data_root / "hydrological" / "raw" / "gauge_water_level_observations.csv"
        ),
        "gauge_danger_levels": data_root / "hydrological" / "raw" / "official_gauge_danger_levels.csv",
        "gauge_grid_crosswalk": data_root / "flood_training" / "gauge_grid_crosswalk.csv",
        "gauge_coverage_evidence": (
            data_root / "flood_training" / "gauge_coverage_evidence.csv"
        ),
        "verified_window_labels": data_root / "flood_training" / "gauge_danger_level_labels.csv",
        "window_assessments": data_root / "flood_training" / "window_assessments.csv",
        "historical_weather_archive": (
            data_root / "raw_sources" / "open_meteo" / "archive.json"
        ),
        "weather_archive_manifest": (
            data_root / "raw_sources" / "open_meteo" / "archive.manifest.json"
        ),
        "source_metadata": data_root / "flood_training" / "source_metadata.json",
        "licensing_evidence": data_root / "flood_training" / "licensing_evidence.json",
        "prepared_predictors": data_root / "flood_training" / "prepared_predictors.csv",
    }
    files = {
        name: {
            "path": str(path.relative_to(root)),
            "available": path.is_file(),
        }
        for name, path in evidence.items()
    }
    missing = [name for name, item in files.items() if not item["available"]]
    observations_path = evidence["historical_gauge_observations"]
    danger_path = evidence["gauge_danger_levels"]
    mapping_path = evidence["gauge_grid_crosswalk"]
    coverage_path = evidence["gauge_coverage_evidence"]
    assessments_path = evidence["window_assessments"]
    weather_path = evidence["historical_weather_archive"]
    weather_manifest_path = evidence["weather_archive_manifest"]
    source_metadata_path = evidence["source_metadata"]
    licensing_path = evidence["licensing_evidence"]

    requirements: dict[str, dict[str, Any]] = {
        "official_danger_levels": _requirement(
            "MISSING" if not danger_path.is_file() else "PRESENT_UNVERIFIED",
            str(danger_path.relative_to(root)),
            "Requires an authoritative per-gauge threshold register, effective dates, units, datum, source authority, and reuse permission.",
        ),
        "matching_vertical_datums": _requirement(
            "MISSING",
            str(danger_path.relative_to(root)),
            "No declared datum comparison is possible until observations and danger-level files are present.",
        ),
        "complete_observation_coverage": _requirement(
            "MISSING" if not coverage_path.is_file() else "PRESENT_UNVERIFIED",
            str(coverage_path.relative_to(root)),
            "Coverage rows and cadence declarations are not provider-authenticated; complete windows require source evidence.",
        ),
        "verified_negative_windows": _requirement(
            "MISSING",
            str(assessments_path.relative_to(root)),
            "Importer assessments are candidate checks only; no assessment output can authenticate negative-window evidence or create labels.",
        ),
        "reviewed_gauge_to_weather_mapping": _requirement(
            "MISSING" if not mapping_path.is_file() else "PRESENT_UNVERIFIED",
            str(mapping_path.relative_to(root)),
            "A declared review does not establish catchment representativeness, hydrologic connectivity, or scientific approval.",
        ),
        "historical_weather_coverage": _requirement(
            "MISSING" if not weather_path.is_file() else "PRESENT_UNVERIFIED",
            str(weather_path.relative_to(root)),
            "Archive presence does not establish dates, gauge/grid alignment, adequate multi-site coverage, or acceptable source terms.",
        ),
        "licensing_evidence": _requirement(
            "MISSING" if not licensing_path.is_file() else "PRESENT_UNVERIFIED",
            str(licensing_path.relative_to(root)),
            "Retain source-specific license or written authorization evidence; a URL or operator declaration alone is not permission.",
        ),
        "domain_target_approval": _requirement(
            "MISSING" if not evidence["approved_target_review"].is_file() else "PRESENT_UNVERIFIED",
            str(evidence["approved_target_review"].relative_to(root)),
            "The proposed 24-hour gauge-threshold target requires documented domain approval.",
        ),
        "model_evaluation": _requirement(
            "NOT_AVAILABLE",
            None,
            "No model may be trained until source evidence, labels, and target approval pass review; no valid evaluation is recorded.",
        ),
    }

    danger_columns = (
        "gauge_id",
        "threshold_record_id",
        "effective_from",
        "effective_to",
        "danger_level_m",
        "vertical_datum",
        "unit",
    )
    if danger_path.is_file() and not observations_path.is_file():
        thresholds, threshold_error = _csv_rows(danger_path, danger_columns)
        if threshold_error:
            requirements["official_danger_levels"] = _requirement(
                "SYNTACTICALLY_INVALID",
                str(danger_path.relative_to(root)),
                threshold_error,
            )
            requirements["official_danger_levels"]["syntax_status"] = "INVALID"
        else:
            requirements["official_danger_levels"] = _requirement(
                "SYNTACTICALLY_VALID_UNVERIFIED",
                str(danger_path.relative_to(root)),
                f"{len(thresholds)} threshold row(s) parse with the required columns; authority, effective history, datum, and terms remain unverified.",
            )
            requirements["official_danger_levels"]["syntax_status"] = "VALID"

    if observations_path.is_file() and danger_path.is_file():
        observation_columns = (
            "gauge_id",
            "observed_at",
            "water_level_m",
            "vertical_datum",
            "quality_flag",
        )
        observations, observation_error = _csv_rows(observations_path, observation_columns)
        thresholds, threshold_error = _csv_rows(danger_path, danger_columns)
        if threshold_error:
            requirements["official_danger_levels"] = _requirement(
                "SYNTACTICALLY_INVALID",
                str(danger_path.relative_to(root)),
                threshold_error,
            )
        else:
            requirements["official_danger_levels"] = _requirement(
                "SYNTACTICALLY_VALID_UNVERIFIED",
                str(danger_path.relative_to(root)),
                f"{len(thresholds)} threshold row(s) parse with the required columns; authority, effective history, datum, and terms remain unverified.",
            )
            requirements["official_danger_levels"]["syntax_status"] = "VALID"
        if observation_error or threshold_error:
            requirements["matching_vertical_datums"] = _requirement(
                "SYNTACTICALLY_INVALID",
                str(danger_path.relative_to(root)),
                f"Observation CSV: {observation_error or 'parsed'}; danger-level CSV: {threshold_error or 'parsed'}.",
            )
            requirements["matching_vertical_datums"]["syntax_status"] = "INVALID"
        else:
            observation_datums: dict[str, set[str]] = {}
            threshold_datums: dict[str, set[str]] = {}
            for row in observations:
                gauge_id = row.get("gauge_id", "").strip()
                datum = row.get("vertical_datum", "").strip()
                if gauge_id:
                    observation_datums.setdefault(gauge_id, set()).add(datum)
            for row in thresholds:
                gauge_id = row.get("gauge_id", "").strip()
                datum = row.get("vertical_datum", "").strip()
                if gauge_id:
                    threshold_datums.setdefault(gauge_id, set()).add(datum)
            common_gauges = set(observation_datums) & set(threshold_datums)
            mismatched = [
                gauge
                for gauge in common_gauges
                if observation_datums[gauge] != threshold_datums[gauge]
            ]
            unresolved = [
                gauge
                for gauge in common_gauges
                if any(
                    value.upper() in UNKNOWN_DATUMS
                    for value in observation_datums[gauge] | threshold_datums[gauge]
                )
            ]
            if mismatched:
                datum_status = "DECLARED_MISMATCH"
                datum_details = f"Declared observation and threshold datum values differ for {len(mismatched)} gauge(s)."
            elif unresolved or not common_gauges:
                datum_status = "UNKNOWN_OR_UNMATCHED"
                datum_details = (
                    "No common gauge with fully declared datum values was found."
                    if not common_gauges
                    else f"Datum is unknown or unverified for {len(unresolved)} common gauge(s)."
                )
            else:
                datum_status = "DECLARED_MATCH_UNVERIFIED"
                datum_details = (
                    f"Declared datums match for {len(common_gauges)} gauge(s); source and datum authority "
                    "still require external verification."
                )
            requirements["matching_vertical_datums"] = _requirement(
                datum_status,
                str(danger_path.relative_to(root)),
                datum_details,
            )
            requirements["matching_vertical_datums"]["syntax_status"] = "VALID"

    if coverage_path.is_file():
        coverage_rows, coverage_error = _csv_rows(
            coverage_path,
            (
                "gauge_id",
                "window_start_utc",
                "window_end_utc",
                "expected_interval_minutes",
                "complete_status",
                "evidence_reference",
                "source_record_id",
            ),
        )
        if coverage_error:
            requirements["complete_observation_coverage"] = _requirement(
                "SYNTACTICALLY_INVALID",
                str(coverage_path.relative_to(root)),
                coverage_error,
            )
            requirements["complete_observation_coverage"]["syntax_status"] = "INVALID"
        else:
            complete_declarations = sum(
                row.get("complete_status", "").strip().upper() == "CONFIRMED_COMPLETE"
                for row in coverage_rows
            )
            requirements["complete_observation_coverage"] = _requirement(
                "DECLARED_COMPLETE_UNVERIFIED" if complete_declarations else "NO_COMPLETE_WINDOWS_DECLARED",
                str(coverage_path.relative_to(root)),
                f"{complete_declarations} row(s) declare complete coverage; declarations need source verification.",
            )
            requirements["complete_observation_coverage"]["syntax_status"] = "VALID"

    if mapping_path.is_file():
        mapping_rows, mapping_error = _csv_rows(
            mapping_path,
            (
                "gauge_id",
                "grid_location_id",
                "gauge_latitude",
                "gauge_longitude",
                "grid_latitude",
                "grid_longitude",
                "approved_max_distance_km",
                "review_status",
                "reviewer",
                "reviewed_at_utc",
                "reference",
                "matching_method",
            ),
        )
        if mapping_error:
            requirements["reviewed_gauge_to_weather_mapping"] = _requirement(
                "SYNTACTICALLY_INVALID",
                str(mapping_path.relative_to(root)),
                mapping_error,
            )
            requirements["reviewed_gauge_to_weather_mapping"]["syntax_status"] = "INVALID"
        else:
            approved = sum(
                row.get("review_status", "").strip().upper() == "APPROVED"
                for row in mapping_rows
            )
            requirements["reviewed_gauge_to_weather_mapping"] = _requirement(
                "DECLARED_APPROVED_UNVERIFIED" if approved else "NOT_APPROVED",
                str(mapping_path.relative_to(root)),
                f"{approved} mapping row(s) declare approval; catchment suitability requires independent scientific review.",
            )
            requirements["reviewed_gauge_to_weather_mapping"]["syntax_status"] = "VALID"

    if assessments_path.is_file():
        assessment_rows, assessment_error = _csv_rows(
            assessments_path,
            ("assessment", "gauge_id", "location_id", "prediction_issue_time_utc"),
        )
        if assessment_error:
            requirements["verified_negative_windows"] = _requirement(
                "SYNTACTICALLY_INVALID",
                str(assessments_path.relative_to(root)),
                assessment_error,
            )
            requirements["verified_negative_windows"]["syntax_status"] = "INVALID"
        else:
            candidate_negatives = sum(
                row.get("assessment", "").strip() == "NEGATIVE_EVIDENCE_CHECKS_PASSED"
                for row in assessment_rows
            )
            requirements["verified_negative_windows"] = _requirement(
                "CANDIDATE_CHECKS_ONLY" if candidate_negatives else "NO_CANDIDATE_NEGATIVES",
                str(assessments_path.relative_to(root)),
                f"{candidate_negatives} candidate negative check(s) passed syntactic evidence checks; none is source-verified by this report.",
            )
            requirements["verified_negative_windows"]["syntax_status"] = "VALID"

    if weather_path.is_file() and not weather_manifest_path.is_file():
        requirements["historical_weather_coverage"] = _requirement(
            "ARCHIVE_MANIFEST_MISSING",
            str(weather_manifest_path.relative_to(root)),
            "The original archive file has no acquisition manifest; source checksum, requested/returned location, model, and retrieval coverage cannot be linked.",
        )
    elif weather_path.is_file() and weather_manifest_path.is_file():
        try:
            weather_payload = json.loads(weather_path.read_text(encoding="utf-8"))
            weather_manifest = json.loads(weather_manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            requirements["historical_weather_coverage"] = _requirement(
                "SYNTACTICALLY_INVALID",
                str(weather_path.relative_to(root)),
                f"Weather archive or acquisition manifest could not be parsed as JSON: {error}",
            )
        else:
            try:
                if not isinstance(weather_payload, dict) or not isinstance(weather_manifest, dict):
                    raise ValueError("Archive and acquisition manifest must be JSON objects.")
                if not isinstance(weather_payload.get("daily"), dict) or not isinstance(
                    weather_payload.get("daily_units"), dict
                ):
                    raise ValueError("Archive daily data and units must be JSON objects.")
                requested = weather_manifest["requested_location_wgs84"]
                if not isinstance(requested, dict):
                    raise ValueError("Manifest requested location must be an object.")
                _, weather_quality = build_predictor_frame(
                    weather_payload,
                    requested_latitude=float(requested["latitude"]),
                    requested_longitude=float(requested["longitude"]),
                )
                actual_hash = sha256_file(weather_path)
                if str(weather_manifest.get("retrieved_file_sha256", "")).lower() != actual_hash.lower():
                    raise ValueError("Archive SHA-256 does not match its acquisition manifest.")
                returned = weather_manifest.get("returned_grid_location_wgs84")
                if not isinstance(returned, dict):
                    raise ValueError("Manifest returned grid location must be an object.")
                if (
                    float(returned["latitude"]) != float(weather_payload["latitude"])
                    or float(returned["longitude"]) != float(weather_payload["longitude"])
                ):
                    raise ValueError("Manifest returned grid coordinates do not match the archive.")
            except (KeyError, TypeError, ValueError) as error:
                requirements["historical_weather_coverage"] = _requirement(
                    "SYNTACTICALLY_INVALID",
                    str(weather_path.relative_to(root)),
                    f"Archive feature schema or manifest/hash validation failed: {error}",
                )
                requirements["historical_weather_coverage"]["syntax_status"] = "INVALID"
            else:
                daily = weather_payload["daily"]
                weather_dates = daily["time"]
                missing_days = weather_quality["missing_calendar_days"]
                weather_status = "INCOMPLETE_CALENDAR" if missing_days else "SYNTACTICALLY_VALID_UNVERIFIED"
                requirements["historical_weather_coverage"] = _requirement(
                    weather_status,
                    str(weather_path.relative_to(root)),
                    (
                        f"Manifest hash and predictor schema pass for {len(weather_dates)} daily row(s), "
                        f"{weather_dates[0]} through {weather_dates[-1]}, returned grid "
                        f"({returned.get('latitude')}, {returned.get('longitude')}); "
                        f"{len(missing_days)} calendar day(s) are missing within the returned date range. "
                        "Requested historical date completeness, match to all gauges, source terms, and scientific suitability "
                        "remain unverified."
                    ),
                )
                requirements["historical_weather_coverage"]["syntax_status"] = "VALID"

    if source_metadata_path.is_file() and licensing_path.is_file():
        try:
            metadata = json.loads(source_metadata_path.read_text(encoding="utf-8"))
            license_evidence = json.loads(licensing_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            requirements["licensing_evidence"] = _requirement(
                "SYNTACTICALLY_INVALID",
                str(licensing_path.relative_to(root)),
                f"License evidence JSON could not be parsed: {error}",
            )
        else:
            if not isinstance(metadata, dict) or not isinstance(license_evidence, dict):
                requirements["licensing_evidence"] = _requirement(
                    "SYNTACTICALLY_INVALID",
                    str(licensing_path.relative_to(root)),
                    "Both source metadata and license evidence JSON must be objects.",
                )
                requirements["licensing_evidence"]["syntax_status"] = "INVALID"
            else:
                metadata_sources = metadata.get("sources")
                license_sources = license_evidence.get("sources")
                if not isinstance(metadata_sources, dict) or not isinstance(license_sources, dict):
                    requirements["licensing_evidence"] = _requirement(
                        "SYNTACTICALLY_INVALID",
                        str(licensing_path.relative_to(root)),
                        "Both JSON files must contain a 'sources' object.",
                    )
                    requirements["licensing_evidence"]["syntax_status"] = "INVALID"
                else:
                    required_sources = {
                        "observations",
                        "danger_levels",
                        "crosswalk",
                        "coverage",
                        "predictors",
                    }
                    missing_license_sources = sorted(required_sources - set(license_sources))
                    missing_metadata_sources = sorted(required_sources - set(metadata_sources))
                    required_license_fields = (
                        "license_name",
                        "evidence_reference",
                        "applicable_uses",
                        "redistribution_terms",
                        "reviewer",
                        "reviewed_at_utc",
                    )
                    incomplete_license_fields = []
                    for source in required_sources & set(license_sources):
                        entry = license_sources[source]
                        if not isinstance(entry, dict):
                            incomplete_license_fields.append(f"{source} (must be an object)")
                            continue
                        incomplete_license_fields.extend(
                            f"{source}.{field}"
                            for field in required_license_fields
                            if not str(entry.get(field, "")).strip()
                        )
                    for source in required_sources & set(metadata_sources):
                        entry = metadata_sources[source]
                        if not isinstance(entry, dict):
                            incomplete_license_fields.append(
                                f"source_metadata.{source} (must be an object)"
                            )
                            continue
                        incomplete_license_fields.extend(
                            f"source_metadata.{source}.{field}"
                            for field in ("license_status", "license_reference", "license_evidence_reference")
                            if not str(entry.get(field, "")).strip()
                        )
                    if missing_license_sources or missing_metadata_sources or incomplete_license_fields:
                        issues = []
                        if missing_license_sources:
                            issues.append("missing license sources: " + ", ".join(missing_license_sources))
                        if missing_metadata_sources:
                            issues.append("missing metadata sources: " + ", ".join(missing_metadata_sources))
                        if incomplete_license_fields:
                            issues.append("missing fields: " + ", ".join(incomplete_license_fields))
                        requirements["licensing_evidence"] = _requirement(
                            "PRESENT_INCOMPLETE_UNVERIFIED",
                            str(licensing_path.relative_to(root)),
                            "License declarations are incomplete (" + "; ".join(issues) + ").",
                        )
                        requirements["licensing_evidence"]["syntax_status"] = "VALID"
                    else:
                        requirements["licensing_evidence"] = _requirement(
                            "PRESENT_UNVERIFIED",
                            str(licensing_path.relative_to(root)),
                            (
                                f"{len(metadata_sources)} source metadata entries and {len(license_sources)} license evidence "
                                "entries parse. A reviewer must verify each source's applicable terms."
                            ),
                        )
                        requirements["licensing_evidence"]["syntax_status"] = "VALID"

    blocking = [
        name
        for name, item in requirements.items()
        if item["status"] not in {"VERIFIED", "APPROVED"}
    ]
    from ml.preprocessing.flood_gauge_package_preflight import (
        get_gauge_package_preflight,
    )

    gauge_package_preflight = get_gauge_package_preflight(root)
    return {
        "status": "NOT_READY",
        "target_id": TARGET_ID,
        "target_status": TARGET_DEFINITION_STATUS,
        "target_definition": TARGET_DEFINITION,
        "prediction_horizon_hours": 24,
        "files": files,
        "missing_evidence": missing,
        "requirements": requirements,
        "blocking_requirements": blocking,
        "gauge_package_preflight": gauge_package_preflight,
        "evidence_boundary": (
            "File presence, parsing, declared approvals, and importer checks are not proof of source "
            "authority, licensing, scientific suitability, or verified labels. This service does not "
            "promote readiness to READY."
        ),
        "message": (
            "Flood prediction remains NOT_READY. Review each requirement independently; files and "
            "syntactic checks do not establish external evidence or scientific approval."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Report flood data readiness without promoting it.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = get_flood_target_readiness(args.root)
    serialized = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")


if __name__ == "__main__":
    main()
