import json
from pathlib import Path

import pytest

from app.services.gis_readiness_service import (
    _validate_geojson,
    get_gis_data_readiness,
)


def _write_geojson(path: Path, coordinates: list, crs: str = "EPSG:4326") -> Path:
    path.write_text(
        json.dumps({
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": crs}},
            "features": [{
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Point", "coordinates": coordinates},
            }],
        }),
        encoding="utf-8",
    )
    return path


def test_valid_geojson_crs_and_coverage_are_checked(tmp_path: Path) -> None:
    result = _validate_geojson(_write_geojson(tmp_path / "inside.geojson", [76.25, 9.95]))

    assert result["valid"] is True
    assert result["crs"] == "EPSG:4326"
    assert result["feature_count"] == 1
    assert result["bounds"] == (76.25, 9.95, 76.25, 9.95)


def test_geojson_outside_kochI_coverage_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not overlap"):
        _validate_geojson(_write_geojson(tmp_path / "outside.geojson", [80.0, 17.0]))


def test_geojson_invalid_crs_and_nonfinite_coordinates_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Expected WGS 84"):
        _validate_geojson(_write_geojson(tmp_path / "wrong-crs.geojson", [76.25, 9.95], "EPSG:3857"))
    with pytest.raises(ValueError, match="non-finite"):
        _validate_geojson(_write_geojson(tmp_path / "nan.geojson", [float("nan"), 9.95]))


def test_actual_gis_inventory_reports_verified_local_layers() -> None:
    project_root = Path(__file__).resolve().parents[2]

    result = get_gis_data_readiness(project_root)

    assert result["study_area"] == "Kochi, Kerala, India"
    assert result["validated_layers"] == 7
    assert result["expected_layers"] == 7
    assert result["status"] == "READY"
    assert result["risk_map_uses_static_layers"] is False
    assert result["layers"]["elevation"]["crs"] == "EPSG:4326"
