from collections.abc import Mapping
from typing import Any

import folium

from gis.layers.disaster_layer import add_disaster_layer
from gis.layers.infrastructure_layer import add_infrastructure_layer
from gis.layers.geographic_layer import add_geographic_layer
from gis.layers.risk_layer import add_risk_layer
from gis.maps.base_map import create_base_map
from gis.visualization.risk_visualization import add_risk_legend


def create_risk_map(
    risk_points: dict[str, Any],
    *,
    disasters: dict[str, Any] | None = None,
    infrastructure: dict[str, Any] | None = None,
    geographic_layers: Mapping[str, dict[str, Any]] | None = None,
    center: tuple[float, float] = (22.5, 80.0),
    zoom_start: int = 5,
) -> folium.Map:
    """Compose the base map, risk layer and optional GIS context layers."""
    map_object = create_base_map(center=center, zoom_start=zoom_start)
    add_risk_layer(map_object, risk_points)
    if disasters is not None:
        add_disaster_layer(map_object, disasters)
    if infrastructure is not None:
        add_infrastructure_layer(map_object, infrastructure)
    for layer_name, collection in (geographic_layers or {}).items():
        add_geographic_layer(map_object, collection, name=layer_name)
    add_risk_legend(map_object)
    folium.LayerControl(collapsed=False).add_to(map_object)
    return map_object
