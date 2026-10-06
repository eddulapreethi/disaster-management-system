from typing import Any

import folium

from gis.gis_processing import validate_feature_collection
from gis.visualization.risk_visualization import risk_color


def add_risk_layer(
    map_object: folium.Map,
    feature_collection: dict[str, Any],
    *,
    name: str = "Disaster risk",
    show: bool = True,
) -> folium.FeatureGroup:
    """Add backend-compatible risk-point GeoJSON as colored circle markers."""
    collection = validate_feature_collection(feature_collection)
    group = folium.FeatureGroup(name=name, show=show)
    for feature in collection["features"]:
        longitude, latitude = feature["geometry"]["coordinates"][:2]
        properties = feature.get("properties", {})
        color = risk_color(properties.get("risk_level", "unknown"))
        score = properties.get("risk_score", "n/a")
        disaster_type = str(properties.get("disaster_type", "Risk point"))
        folium.CircleMarker(
            location=[latitude, longitude],
            radius=7,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.78,
            weight=2,
            tooltip=f"{disaster_type}: {score} ({properties.get('risk_level', 'unknown')})",
        ).add_to(group)
    group.add_to(map_object)
    return group
