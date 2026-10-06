import json
import math
from pathlib import Path
from typing import Any

GeoJSON = dict[str, Any]
EARTH_RADIUS_KM = 6371.0088


def validate_feature_collection(data: GeoJSON) -> GeoJSON:
    """Validate a GeoJSON FeatureCollection and return it unchanged."""
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError("Expected a GeoJSON FeatureCollection.")
    features = data.get("features")
    if not isinstance(features, list):
        raise ValueError("FeatureCollection 'features' must be a list.")
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"Feature at index {index} is not a GeoJSON Feature.")
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") != "Point":
            raise ValueError(f"Feature at index {index} must have Point geometry.")
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, (list, tuple)) or len(coordinates) < 2:
            raise ValueError(f"Feature at index {index} needs longitude and latitude coordinates.")
        longitude, latitude = coordinates[:2]
        if not _valid_coordinate(longitude, -180, 180) or not _valid_coordinate(latitude, -90, 90):
            raise ValueError(f"Feature at index {index} has invalid longitude or latitude.")
        if not isinstance(feature.get("properties", {}), dict):
            raise ValueError(f"Feature at index {index} properties must be an object.")
    return data


def validate_geographic_collection(data: GeoJSON) -> GeoJSON:
    """Validate common GeoJSON point, line, polygon and multi-geometries."""
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError("Expected a GeoJSON FeatureCollection.")
    features = data.get("features")
    if not isinstance(features, list):
        raise ValueError("FeatureCollection 'features' must be a list.")
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"Feature at index {index} is not a GeoJSON Feature.")
        if not isinstance(feature.get("properties", {}), dict):
            raise ValueError(f"Feature at index {index} properties must be an object.")
        _validate_geometry(feature.get("geometry"), index)
    return data


def load_geojson(path: str | Path) -> GeoJSON:
    """Load and validate a point, line or polygon GeoJSON FeatureCollection."""
    with Path(path).open(encoding="utf-8") as geojson_file:
        data = json.load(geojson_file)
    return validate_geographic_collection(data)


def make_point_feature(
    longitude: float,
    latitude: float,
    properties: dict[str, Any] | None = None,
    *,
    feature_id: str | int | None = None,
) -> GeoJSON:
    """Create a validated GeoJSON Point Feature using standard lon/lat order."""
    if not _valid_coordinate(longitude, -180, 180) or not _valid_coordinate(latitude, -90, 90):
        raise ValueError("Longitude must be within [-180, 180] and latitude within [-90, 90].")
    feature: GeoJSON = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [float(longitude), float(latitude)]},
        "properties": properties or {},
    }
    if feature_id is not None:
        feature["id"] = feature_id
    return feature


def make_feature_collection(features: list[GeoJSON]) -> GeoJSON:
    """Create and validate a GeoJSON FeatureCollection."""
    return validate_feature_collection({"type": "FeatureCollection", "features": features})


def haversine_distance_km(
    longitude_a: float,
    latitude_a: float,
    longitude_b: float,
    latitude_b: float,
) -> float:
    """Calculate great-circle distance between two longitude/latitude points."""
    for longitude, latitude in ((longitude_a, latitude_a), (longitude_b, latitude_b)):
        if not _valid_coordinate(longitude, -180, 180) or not _valid_coordinate(latitude, -90, 90):
            raise ValueError("Coordinates must be finite longitude/latitude values in valid ranges.")
    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    haversine = math.sin(delta_lat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    central_angle = 2 * math.asin(math.sqrt(min(1.0, haversine)))
    return EARTH_RADIUS_KM * central_angle


def filter_points_within_radius(
    feature_collection: GeoJSON,
    longitude: float,
    latitude: float,
    radius_km: float,
) -> GeoJSON:
    """Return features within radius_km of a center point."""
    collection = validate_feature_collection(feature_collection)
    if not math.isfinite(radius_km) or radius_km < 0:
        raise ValueError("radius_km must be a finite non-negative number.")
    nearby = []
    for feature in collection["features"]:
        feature_lon, feature_lat = feature["geometry"]["coordinates"][:2]
        if haversine_distance_km(longitude, latitude, feature_lon, feature_lat) <= radius_km:
            nearby.append(feature)
    return {"type": "FeatureCollection", "features": nearby}


def _valid_coordinate(value: Any, minimum: float, maximum: float) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and minimum <= value <= maximum
    )


def _validate_geometry(geometry: Any, feature_index: int) -> None:
    if not isinstance(geometry, dict):
        raise ValueError(f"Feature at index {feature_index} must contain a geometry object.")
    geometry_type = geometry.get("type")
    if geometry_type == "GeometryCollection":
        geometries = geometry.get("geometries")
        if not isinstance(geometries, list):
            raise ValueError(f"Feature at index {feature_index} has invalid GeometryCollection.")
        for child in geometries:
            _validate_geometry(child, feature_index)
        return

    minimum_positions = {
        "Point": 1,
        "MultiPoint": 1,
        "LineString": 2,
        "MultiLineString": 2,
        "Polygon": 4,
        "MultiPolygon": 4,
    }.get(geometry_type)
    if minimum_positions is None:
        raise ValueError(f"Feature at index {feature_index} has unsupported geometry {geometry_type!r}.")

    positions = list(_iter_positions(geometry.get("coordinates"), geometry_type))
    if len(positions) < minimum_positions:
        raise ValueError(f"Feature at index {feature_index} has too few coordinates for {geometry_type}.")
    for position in positions:
        if not isinstance(position, (list, tuple)) or len(position) < 2:
            raise ValueError(f"Feature at index {feature_index} contains an invalid coordinate position.")
        longitude, latitude = position[:2]
        if not _valid_coordinate(longitude, -180, 180) or not _valid_coordinate(latitude, -90, 90):
            raise ValueError(f"Feature at index {feature_index} has invalid longitude or latitude.")


def _iter_positions(coordinates: Any, geometry_type: str):
    if geometry_type == "Point":
        yield coordinates
        return
    if geometry_type in {"MultiPoint", "LineString"}:
        yield from coordinates if isinstance(coordinates, (list, tuple)) else ()
        return
    if geometry_type in {"MultiLineString", "Polygon"}:
        for line in coordinates if isinstance(coordinates, (list, tuple)) else ():
            yield from line if isinstance(line, (list, tuple)) else ()
        return
    if geometry_type == "MultiPolygon":
        for polygon in coordinates if isinstance(coordinates, (list, tuple)) else ():
            for ring in polygon if isinstance(polygon, (list, tuple)) else ():
                yield from ring if isinstance(ring, (list, tuple)) else ()
