from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ml.preprocessing import acquire_open_meteo_archive
from ml.preprocessing.reanalysis_archive import (
    ERA5CDSRequestAdapter,
    ERA5LandCDSRequestAdapter,
    PRODUCT_DATASET_IDS,
    RequestLimits,
    VariableMetadata,
    canonical_request_json,
    create_extract_manifest,
    request_sha256,
    serialize_manifest,
    transition_manifest,
    validate_manifest,
    validate_reanalysis_request,
)


def request_payload(**changes):
    request = {
        "product": "ERA5",
        "dataset_id": PRODUCT_DATASET_IDS["ERA5"],
        "variables": ["2m_temperature", "total_precipitation"],
        "start_date": "2024-01-01",
        "end_date": "2024-01-01",
        "times_utc": ["00:00", "12:00"],
        "area": {"west": 76, "south": 9, "east": 77, "north": 10},
        "output_format": "netcdf",
    }
    request.update(changes)
    return request


def manifest():
    return create_extract_manifest(
        request_payload(),
        requested_at_utc=datetime(2024, 1, 2, tzinfo=timezone.utc),
        source_terms_reference="https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels",
        source_terms_status="ACCEPTED",
    )


@pytest.mark.parametrize(
    ("product", "dataset_id"),
    [
        ("ERA5", "reanalysis-era5-single-levels"),
        ("ERA5-Land", "reanalysis-era5-land"),
    ],
)
def test_product_identity_and_dataset_id_consistency(product, dataset_id):
    request = request_payload(product=product, dataset_id=dataset_id)
    assert validate_reanalysis_request(request).dataset_id == dataset_id

    with pytest.raises(ValidationError, match="requires CDS dataset_id"):
        validate_reanalysis_request(request_payload(product=product, dataset_id="wrong-dataset"))


def test_product_specific_release_statuses_are_enforced():
    land_request = request_payload(
        product="ERA5-Land",
        dataset_id=PRODUCT_DATASET_IDS["ERA5-Land"],
        variables=["2m_temperature"],
    )
    land_manifest = create_extract_manifest(
        land_request,
        requested_at_utc=datetime(2024, 1, 2, tzinfo=timezone.utc),
        source_terms_reference="CDS dataset terms",
    )
    assert land_manifest.release_status == "UNKNOWN"

    invalid = land_manifest.model_dump(mode="json")
    invalid["release_status"] = "ERA5T"
    with pytest.raises(ValidationError, match="Invalid release_status"):
        validate_manifest(invalid)


@pytest.mark.parametrize(
    "role",
    [
        "ATMOSPHERIC_ANALYSIS",
        "LAND_MODEL_OUTPUT",
        "INTERPOLATED_ERA5_FORCING",
        "UNKNOWN",
    ],
)
def test_variable_provenance_roles_are_validated(role):
    metadata = VariableMetadata(
        product_identity="ERA5-Land",
        variable_id="2m_temperature",
        native_unit="K",
        temporal_kind="instantaneous",
        role=role,
        role_evidence_reference=(
            "https://confluence.ecmwf.int/display/CKB/ERA5-Land%3A+data+documentation"
        ),
    )
    assert metadata.role == role


def test_era5_land_forcing_and_land_model_outputs_remain_distinct():
    land_request = request_payload(
        product="ERA5-Land",
        dataset_id=PRODUCT_DATASET_IDS["ERA5-Land"],
        variables=["2m_temperature", "total_runoff"],
    )
    value = create_extract_manifest(
        land_request,
        requested_at_utc=datetime(2024, 1, 2, tzinfo=timezone.utc),
        source_terms_reference="CDS dataset terms",
    )
    by_id = {item.variable_id: item for item in value.variables}
    assert by_id["2m_temperature"].role == "INTERPOLATED_ERA5_FORCING"
    assert by_id["total_runoff"].role == "LAND_MODEL_OUTPUT"
    assert all(item.product_identity == "ERA5-Land" for item in value.variables)
    assert all(item.role_evidence_reference.startswith("https://") for item in value.variables)

    promoted = value.model_dump(mode="json")
    promoted["variables"][0]["role"] = "LAND_MODEL_OUTPUT"
    with pytest.raises(ValidationError, match="Invalid provenance role"):
        validate_manifest(promoted)


def test_unknown_provenance_is_preserved_and_missing_evidence_is_rejected():
    value = manifest().model_dump(mode="json")
    value["variables"][0]["role"] = "UNKNOWN"
    unknown_manifest = validate_manifest(value)
    assert unknown_manifest.variables[0].role == "UNKNOWN"

    missing_evidence = unknown_manifest.model_dump(mode="json")
    del missing_evidence["variables"][0]["role_evidence_reference"]
    with pytest.raises(ValidationError, match="role_evidence_reference"):
        validate_manifest(missing_evidence)

    bad_reference = unknown_manifest.model_dump(mode="json")
    bad_reference["variables"][0]["role_evidence_reference"] = "unverified"
    with pytest.raises(ValidationError, match="HTTPS source reference"):
        validate_manifest(bad_reference)

    wrong_product = unknown_manifest.model_dump(mode="json")
    wrong_product["variables"][0]["product_identity"] = "ERA5-Land"
    with pytest.raises(ValidationError, match="product_identity must match"):
        validate_manifest(wrong_product)


@pytest.mark.parametrize(
    ("adapter", "product", "dataset_id", "serializer_id"),
    [
        (
            ERA5CDSRequestAdapter,
            "ERA5",
            "reanalysis-era5-single-levels",
            "era5-single-levels-candidate-v1",
        ),
        (
            ERA5LandCDSRequestAdapter,
            "ERA5-Land",
            "reanalysis-era5-land",
            "era5-land-candidate-v1",
        ),
    ],
)
def test_product_specific_cds_adapters_emit_non_executable_candidates(
    adapter, product, dataset_id, serializer_id
):
    area = {"west": 76, "south": 9, "east": 77, "north": 10}
    request = request_payload(
        product=product,
        dataset_id=dataset_id,
        variables=["2m_temperature"],
        area=area,
    )
    candidate = adapter.serialize(request)
    assert candidate.product_identity == product
    assert candidate.dataset_id == dataset_id
    assert candidate.serializer_id == serializer_id
    assert candidate.status == "UNVERIFIED_CANDIDATE"
    assert candidate.executable is False
    assert candidate.normalized_request.area.model_dump() == area
    assert candidate.candidate_payload["area"] == [10, 76, 9, 77]
    assert candidate.candidate_payload["variable"] == ["2m_temperature"]
    assert candidate.candidate_payload["year"] == ["2024"]
    assert candidate.candidate_payload["month"] == ["01"]
    assert candidate.candidate_payload["day"] == ["01"]
    assert candidate.candidate_payload["time"] == ["00:00", "12:00"]
    assert "grid" not in candidate.candidate_payload
    assert "product_type" not in candidate.candidate_payload
    assert "data_format" not in candidate.candidate_payload
    assert candidate.output_format_candidate == "netcdf"
    assert any("format" in item.lower() for item in candidate.confirmation_required)


def test_cds_adapters_reject_cross_product_requests_and_cannot_confirm_candidates():
    with pytest.raises(ValueError, match="cannot serialize product"):
        ERA5CDSRequestAdapter.serialize(
            request_payload(
                product="ERA5-Land",
                dataset_id=PRODUCT_DATASET_IDS["ERA5-Land"],
            )
        )

    candidate = ERA5CDSRequestAdapter.serialize(request_payload())
    altered_candidate = candidate.model_dump(mode="python")
    altered_candidate["executable"] = True
    with pytest.raises(ValidationError):
        type(candidate).model_validate(altered_candidate)


def test_request_requires_allowlisted_variables_and_configured_variable_limit():
    with pytest.raises(ValidationError, match="Unsupported ERA5 variable"):
        validate_reanalysis_request(request_payload(variables=["made_up_variable"]))
    with pytest.raises(ValueError, match="configured maximum is 1"):
        validate_reanalysis_request(
            request_payload(),
            RequestLimits(max_variables=1),
        )
    with pytest.raises(ValueError, match="configured maximum is 2"):
        validate_reanalysis_request(
            request_payload(
                product="ERA5-Land",
                dataset_id=PRODUCT_DATASET_IDS["ERA5-Land"],
                variables=["2m_temperature", "total_precipitation", "total_runoff"],
            ),
            RequestLimits(max_variables=2),
        )


def test_request_rejects_invalid_and_antimeridian_areas():
    with pytest.raises(ValidationError, match="Antimeridian-crossing"):
        validate_reanalysis_request(
            request_payload(area={"west": 170, "south": -1, "east": -170, "north": 1})
        )
    with pytest.raises(ValidationError, match="Area south must be less than north"):
        validate_reanalysis_request(
            request_payload(area={"west": 76, "south": 10, "east": 77, "north": 9})
        )
    with pytest.raises(ValidationError):
        validate_reanalysis_request(
            request_payload(area={"west": -181, "south": 9, "east": 77, "north": 10})
        )
    with pytest.raises(ValueError, match="configured maximum"):
        validate_reanalysis_request(
            request_payload(area={"west": 70, "south": 9, "east": 72, "north": 10})
        )


def test_request_requires_explicit_dates_times_and_respects_duration():
    with pytest.raises(ValidationError, match="YYYY-MM-DD"):
        validate_reanalysis_request(request_payload(start_date="2024-1-1"))
    with pytest.raises(ValidationError, match="on or after"):
        validate_reanalysis_request(
            request_payload(start_date="2024-01-02", end_date="2024-01-01")
        )
    with pytest.raises(ValidationError, match="at least one explicit UTC hour"):
        validate_reanalysis_request(request_payload(times_utc=[]))
    with pytest.raises(ValidationError, match="explicit hourly UTC times"):
        validate_reanalysis_request(request_payload(times_utc=["12:30"]))
    with pytest.raises(ValueError, match="configured maximum is 1 day"):
        validate_reanalysis_request(
            request_payload(end_date="2024-01-02"),
            RequestLimits(max_time_span_days=1),
        )
    assert validate_reanalysis_request(
        request_payload(end_date="2024-01-02"),
        RequestLimits(max_time_span_days=2),
    )


def test_request_rejects_unsupported_format_and_invalid_coordinates():
    with pytest.raises(ValidationError):
        validate_reanalysis_request(request_payload(output_format="csv"))
    with pytest.raises(ValidationError):
        validate_reanalysis_request(
            request_payload(area={"west": 76, "south": 91, "east": 77, "north": 92})
        )


def test_request_hash_is_canonical_and_changes_for_request_dimensions():
    base = request_payload()
    equivalent = request_payload(
        variables=["total_precipitation", "2m_temperature"],
        times_utc=["12:00", "00:00"],
        area={"west": 76.0, "south": 9.0, "east": 77.0, "north": 10.0},
        output_format="NETCDF",
    )
    assert canonical_request_json(base) == canonical_request_json(equivalent)
    assert request_sha256(base) == request_sha256(equivalent)

    variations = [
        {"product": "ERA5-Land", "dataset_id": PRODUCT_DATASET_IDS["ERA5-Land"]},
        {"dataset_id": "different-dataset"},
        {"variables": ["2m_temperature"]},
        {"start_date": "2024-01-02", "end_date": "2024-01-02"},
        {"times_utc": ["01:00"]},
        {"area": {"west": 76, "south": 9, "east": 76.5, "north": 10}},
        {"output_format": "grib"},
    ]
    base_hash = request_sha256(base)
    for variation in variations:
        changed = deepcopy(base)
        changed.update(variation)
        if variation.get("dataset_id") == "different-dataset":
            with pytest.raises(ValidationError):
                request_sha256(changed)
            continue
        assert request_sha256(changed) != base_hash


def test_custom_limits_do_not_change_request_identity_or_manifest_validation():
    long_request = request_payload(end_date="2024-01-02")
    limits = RequestLimits(max_time_span_days=2)
    manifest_value = create_extract_manifest(
        long_request,
        requested_at_utc=datetime(2024, 1, 3, tzinfo=timezone.utc),
        source_terms_reference="CDS terms",
        source_terms_status="ACCEPTED",
        limits=limits,
    )
    assert validate_manifest(manifest_value).request_sha256 == request_sha256(long_request, limits)


def test_manifest_schema_serialization_and_provenance_validation():
    value = manifest()
    serialized = serialize_manifest(value)
    serialized_manifest = json.loads(serialized)
    assert serialize_manifest(validate_manifest(serialized_manifest)) == serialized
    assert serialized_manifest["contract_version"] == "1.1"
    assert serialized_manifest["provider"] == "ECMWF/Copernicus CDS"
    assert serialized_manifest["lifecycle_state"] == "REQUESTED"
    assert serialized_manifest["source_file"] is None

    missing_terms = value.model_dump(mode="json")
    missing_terms["source_terms_reference"] = ""
    with pytest.raises(ValidationError, match="source_terms_reference"):
        validate_manifest(missing_terms)

    bad_identity = value.model_dump(mode="json")
    bad_identity["dataset_id"] = "different"
    with pytest.raises(ValidationError, match="must match its canonical request"):
        validate_manifest(bad_identity)

    bad_hash = value.model_dump(mode="json")
    bad_hash["request_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="does not match"):
        validate_manifest(bad_hash)

    bad_unit = value.model_dump(mode="json")
    bad_unit["variables"][0]["native_unit"] = "mm"
    with pytest.raises(ValidationError, match="Unsupported native unit"):
        validate_manifest(bad_unit)


def test_secret_like_fields_are_rejected_and_never_serialized():
    secret_request = request_payload()
    secret_request["api_key"] = "must-not-be-recorded"
    with pytest.raises(ValueError, match="Secret-like field"):
        validate_reanalysis_request(secret_request)

    secret_manifest = manifest().model_dump(mode="json")
    secret_manifest["credentials"] = "must-not-be-recorded"
    with pytest.raises(ValueError, match="Secret-like field"):
        validate_manifest(secret_manifest)

    serialized = serialize_manifest(manifest())
    assert "api_key" not in serialized
    assert "client_secret" not in serialized
    assert "authorization" not in serialized


def test_file_presence_alone_cannot_mark_manifest_validated():
    value = manifest().model_dump(mode="json")
    value.update(
        lifecycle_state="DOWNLOADED",
        submitted_at_utc="2024-01-02T00:00:00Z",
    )
    with pytest.raises(ValidationError, match="requires source file metadata"):
        validate_manifest(value)

    value.update(
        lifecycle_state="VALIDATED",
        retrieved_at_utc="2024-01-02T01:00:00Z",
        source_file={
            "file_name": "extract.nc",
            "file_size_bytes": 100,
            "output_format": "netcdf",
            "sha256": "a" * 64,
        },
    )
    with pytest.raises(ValidationError, match="passing validation report"):
        validate_manifest(value)


def test_lifecycle_transitions_validate_prerequisites_and_reject_invalid_edges():
    current = manifest()
    current = transition_manifest(
        current,
        "SUBMITTED",
        updates={"submitted_at_utc": "2024-01-02T00:30:00Z"},
    )
    current = transition_manifest(current, "RETRIEVING")
    current = transition_manifest(
        current,
        "DOWNLOADED",
        updates={
            "retrieved_at_utc": "2024-01-02T01:00:00Z",
            "source_file": {
                "file_name": "extract.nc",
                "file_size_bytes": 100,
                "output_format": "netcdf",
                "sha256": "a" * 64,
            },
        },
    )
    current = transition_manifest(current, "VALIDATING")
    value = current.model_dump(mode="json")
    value["grid"].update(
        latitude_coordinate_name="latitude",
        longitude_coordinate_name="longitude",
        valid_time_coordinate_name="valid_time",
        time_bounds_coordinate_name="time_bounds",
        grid_spacing_degrees=[0.25, 0.25],
    )
    for variable in value["variables"]:
        variable["missing_value_description"] = "Read from the file's declared fill metadata."
        if variable["temporal_kind"] == "accumulation":
            variable["temporal_bounds_description"] = "Accumulation interval recorded per valid time."
            variable["accumulation_semantics"] = "Validated against dataset-specific forecast-step metadata."
    current = validate_manifest(value)
    current = transition_manifest(
        current,
        "VALIDATED",
        updates={
            "validation": {
                "status": "PASSED",
                "validator_version": "test-1",
                "validated_at_utc": "2024-01-02T02:00:00Z",
                "checks": [{"name": "local fixture checks", "status": "PASSED"}],
                "warnings": [],
            }
        },
    )
    assert current.lifecycle_state == "VALIDATED"
    with pytest.raises(ValueError, match="Invalid lifecycle transition"):
        transition_manifest(current, "FAILED", status_detail="terminal state")

    with pytest.raises(ValueError, match="requires status_detail"):
        transition_manifest(manifest(), "FAILED")


def test_submission_requires_dataset_terms_acceptance():
    unaccepted = create_extract_manifest(
        request_payload(),
        requested_at_utc=datetime(2024, 1, 2, tzinfo=timezone.utc),
        source_terms_reference="CDS dataset terms",
    )
    with pytest.raises(ValidationError, match="requires accepted dataset terms"):
        transition_manifest(
            unaccepted,
            "SUBMITTED",
            updates={"submitted_at_utc": "2024-01-02T00:30:00Z"},
        )


def test_manifest_rejects_invalid_file_metadata_and_unknown_updates():
    value = manifest().model_dump(mode="json")
    value.update(
        lifecycle_state="DOWNLOADED",
        submitted_at_utc="2024-01-02T00:30:00Z",
        retrieved_at_utc="2024-01-02T01:00:00Z",
        source_file={
            "file_name": "..\\extract.nc",
            "file_size_bytes": 1,
            "output_format": "netcdf",
            "sha256": "a" * 64,
        },
    )
    with pytest.raises(ValidationError, match="file name, not a path"):
        validate_manifest(value)
    with pytest.raises(ValueError, match="only provide"):
        transition_manifest(manifest(), "FAILED", status_detail="failure", updates={"product": "ERA5"})


def test_reanalysis_module_does_not_change_open_meteo_archive_conventions():
    assert acquire_open_meteo_archive.ARCHIVE_URL == "https://archive-api.open-meteo.com/v1/archive"
    assert acquire_open_meteo_archive.DAILY_VARIABLES == (
        "temperature_2m_mean",
        "precipitation_sum",
        "rain_sum",
        "wind_speed_10m_max",
        "relative_humidity_2m_mean",
    )
