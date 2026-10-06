from typing import Any

import folium

from gis.gis_processing import validate_geographic_collection


def add_geographic_layer(
    map_object: folium.Map,
    feature_collection: dict[str, Any],
    *,
    name: str,
    color: str = "#2878a5",
    show: bool = True,
) -> folium.FeatureGroup:
    """Add GeoJSON boundaries, roads, rivers, lakes or land-use shapes."""
    if not name.strip():
        raise ValueError("Layer name cannot be blank.")
    collection = validate_geographic_collection(feature_collection)
    group = folium.FeatureGroup(name=name, show=show)
    options: dict[str, Any] = {}
    tooltip_fields = _available_tooltip_fields(collection)
    if tooltip_fields:
        options["tooltip"] = folium.GeoJsonTooltip(fields=tooltip_fields)
    folium.GeoJson(
        collection,
        name=name,
        style_function=lambda _feature: {
            "color": color,
            "weight": 2,
            "fillColor": color,
            "fillOpacity": 0.16,
        },
        **options,
    ).add_to(group)
    group.add_to(map_object)
    return group


def _available_tooltip_fields(collection: dict[str, Any]) -> list[str]:
    for feature in collection["features"]:
        properties = feature.get("properties", {})
        if properties:
            return list(properties)[:4]
    return []
