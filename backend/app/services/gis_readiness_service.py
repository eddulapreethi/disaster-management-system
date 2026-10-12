import json
import math
import math
from pathlib import Path
from typing import Any, Iterator

from PIL import Image


STUDY_BOUNDS = (76.0, 9.8, 76.5, 10.1)
GEOGRAPHIC_LAYERS = {
    "administrative_boundaries": "administrative_boundaries/kochi_administrative_boundaries.geojson",
    "lakes": "lakes/kochi_lakes.geojson",
    "land_use": "land_use/kochi_land_use.geojson",
    "rivers": "rivers/kochi_rivers.geojson",
    "roads": "roads/kochi_roads.geojson",
    "watersheds": "watersheds/kochi_watersheds.geojson",
}


def _coordinates(value: Any) -> Iterator[tuple[float, float]]:
    if not isinstance(value, list):
        return
    if (
        len(value) >= 2
        and isinstance(value[0], (int, float))
        and not isinstance(value[0], bool)
        and isinstance(value[1], (int, float))
        and not isinstance(value[1], bool)
    ):
        longitude, latitude = float(value[0]), float(value[1])
        if not math.isfinite(longitude) or not math.isfinite(latitude):
            raise ValueError("Geometry contains non-finite coordinates.")
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise ValueError("Geometry coordinates are outside WGS 84 bounds.")
        yield longitude, latitude
        return
    for item in value:
        yield from _coordinates(item)


def _intersects(bounds: tuple[float, float, float, float]) -> bool:
    west, south, east, north = bounds
    study_west, study_south, study_east, study_north = STUDY_BOUNDS
    return east >= study_west and west <= study_east and north >= study_south and south <= study_north


def _validate_geojson(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError("Expected a GeoJSON FeatureCollection.")
    crs_name = (
        payload.get("crs", {}).get("properties", {}).get("name")
        if isinstance(payload.get("crs"), dict)
        else None
    )
    if crs_name and "4326" not in str(crs_name) and "CRS84" not in str(crs_name).upper():
        raise ValueError(f"Expected WGS 84 coordinates, received CRS {crs_name}.")

    geometry_types: set[str] = set()
    west = south = math.inf
    east = north = -math.inf
    coordinate_count = 0
    for feature in payload["features"]:
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(geometry, dict) or not isinstance(geometry.get("type"), str):
            raise ValueError("Feature has no valid geometry.")
        geometry_types.add(geometry["type"])
        geometries = (
            geometry.get("geometries", [])
            if geometry["type"] == "GeometryCollection"
            else [geometry]
        )
        feature_coordinate_count = 0
        for member in geometries:
            if not isinstance(member, dict):
                raise ValueError("GeometryCollection has an invalid member.")
            for longitude, latitude in _coordinates(member.get("coordinates")):
                west = min(west, longitude)
                south = min(south, latitude)
                east = max(east, longitude)
                north = max(north, latitude)
                feature_coordinate_count += 1
        if not feature_coordinate_count:
            raise ValueError("Feature collection contains no coordinate pairs.")
        coordinate_count += feature_coordinate_count

    if not payload["features"] or not coordinate_count:
        raise ValueError("Feature collection is empty.")
    bounds = (west, south, east, north)
    if not _intersects(bounds):
        raise ValueError("Dataset does not overlap the Kochi study bounds.")
    return {
        "valid": True,
        "format": "GeoJSON",
        "crs": crs_name or "OGC:CRS84 (RFC 7946 default)",
        "feature_count": len(payload["features"]),
        "geometry_types": sorted(geometry_types),
        "bounds": bounds,
        "bytes": path.stat().st_size,
    }


def _validate_dem(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        if image.format != "TIFF" or image.width < 1 or image.height < 1:
            raise ValueError("Expected a readable, non-empty GeoTIFF.")
        tags = image.tag_v2
        scale = tags.get(33550)
        tiepoint = tags.get(33922)
        geokeys = tags.get(34735)
        nodata = tags.get(42113)
        if not scale or not tiepoint or not geokeys or nodata is None:
            raise ValueError("GeoTIFF is missing scale, tiepoint, CRS, or nodata metadata.")
        keys = {
            geokeys[index]: geokeys[index + 3]
            for index in range(4, min(4 + geokeys[3] * 4, len(geokeys)), 4)
        }
        if keys.get(2048) != 4326:
            raise ValueError("DEM GeoTIFF does not declare EPSG:4326.")
        west, north = float(tiepoint[3]), float(tiepoint[4])
        east = west + image.width * float(scale[0])
        south = north - image.height * float(scale[1])
        bounds = (west, south, east, north)
        if not _intersects(bounds):
            raise ValueError("DEM does not overlap the Kochi study bounds.")
        minimum, maximum = image.getextrema()
        nodata_value = float(str(nodata).strip())
        if minimum == maximum or (minimum == nodata_value and maximum == nodata_value):
            raise ValueError("DEM contains a constant elevation value.")
        sample_width = min(image.width, 100)
        sample_height = min(image.height, 100)
        has_valid_sample = any(
            float(image.getpixel((x * image.width // sample_width, y * image.height // sample_height)))
            != nodata_value
            for y in range(sample_height)
            for x in range(sample_width)
        )
        if not has_valid_sample:
            raise ValueError("DEM contains no sampled valid elevation cells.")
        return {
            "valid": True,
            "format": "GeoTIFF",
            "crs": "EPSG:4326",
            "width": image.width,
            "height": image.height,
            "pixel_size_degrees": [float(scale[0]), float(scale[1])],
            "bounds": bounds,
            "nodata": nodata_value if math.isfinite(nodata_value) else str(nodata),
            "value_range": [minimum, maximum],
            "bytes": path.stat().st_size,
        }


def get_gis_data_readiness(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[3]
    data_root = root / "gis" / "data" / "geographic_data"
    layers: dict[str, dict[str, Any]] = {}
    for name, relative_path in GEOGRAPHIC_LAYERS.items():
        path = data_root / relative_path
        try:
            layers[name] = {"path": relative_path, **_validate_geojson(path)}
        except (OSError, ValueError, json.JSONDecodeError) as error:
            layers[name] = {"path": relative_path, "valid": False, "error": str(error)}
    dem_path = data_root / "elevation" / "kochi_dem.tif"
    try:
        layers["elevation"] = {
            "path": str(dem_path.relative_to(root)),
            **_validate_dem(dem_path),
        }
    except (OSError, ValueError) as error:
        layers["elevation"] = {
            "path": str(dem_path.relative_to(root)),
            "valid": False,
            "error": str(error),
        }

    valid_count = sum(layer["valid"] for layer in layers.values())
    status = "READY" if valid_count == len(layers) else "PARTIAL" if valid_count else "UNAVAILABLE"
    return {
        "status": status,
        "message": (
            f"{valid_count} of {len(layers)} local GIS layers passed file, CRS, and Kochi coverage checks. "
            "This verifies map-data files only; no flood-model feature pipeline is implied."
        ),
        "study_area": "Kochi, Kerala, India",
        "study_bounds": STUDY_BOUNDS,
        "validated_layers": valid_count,
        "expected_layers": len(layers),
        "layers": layers,
        "risk_map_uses_static_layers": False,
    }
