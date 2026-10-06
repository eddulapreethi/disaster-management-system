from typing import Any

import folium

from gis.gis_processing import validate_feature_collection


def add_infrastructure_layer(
    map_object: folium.Map,
    feature_collection: dict[str, Any],
    *,
    name: str = "Infrastructure",
    show: bool = False,
) -> folium.FeatureGroup:
    """Add infrastructure points (shelters, hospitals, stations) to a map."""
    collection = validate_feature_collection(feature_collection)
    group = folium.FeatureGroup(name=name, show=show)
    for feature in collection["features"]:
        longitude, latitude = feature["geometry"]["coordinates"][:2]
        properties = feature.get("properties", {})
        label = str(properties.get("name", properties.get("facility_type", "Infrastructure")))
        facility_type = str(properties.get("facility_type", "facility"))
        folium.CircleMarker(
            location=[latitude, longitude],
            radius=5,
            color="#176b87",
            fill=True,
            fill_color="#40a6a6",
            fill_opacity=0.9,
            tooltip=f"{label} ({facility_type})",
        ).add_to(group)
    group.add_to(map_object)
    return group
