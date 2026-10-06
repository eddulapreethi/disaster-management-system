from pathlib import Path
from collections.abc import Mapping
from typing import Any

import folium

from gis.gis_processing import validate_feature_collection, validate_geographic_collection
from gis.maps.risk_map import create_risk_map
from gis.visualization.risk_visualization import save_map


def generate_map(
    risk_points: dict[str, Any],
    output_path: str | Path | None = None,
    *,
    disasters: dict[str, Any] | None = None,
    infrastructure: dict[str, Any] | None = None,
    geographic_layers: Mapping[str, dict[str, Any]] | None = None,
    center: tuple[float, float] = (22.5, 80.0),
    zoom_start: int = 5,
) -> folium.Map:
    """Create an interactive risk map and optionally save it as HTML."""
    validate_feature_collection(risk_points)
    if disasters is not None:
        validate_feature_collection(disasters)
    if infrastructure is not None:
        validate_feature_collection(infrastructure)
    for collection in (geographic_layers or {}).values():
        validate_geographic_collection(collection)

    map_object = create_risk_map(
        risk_points,
        disasters=disasters,
        infrastructure=infrastructure,
        geographic_layers=geographic_layers,
        center=center,
        zoom_start=zoom_start,
    )
    if output_path is not None:
        save_map(map_object, output_path)
    return map_object
