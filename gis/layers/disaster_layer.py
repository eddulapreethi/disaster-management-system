from typing import Any

import folium

from gis.gis_processing import validate_feature_collection


def add_disaster_layer(
    map_object: folium.Map,
    feature_collection: dict[str, Any],
    *,
    name: str = "Reported disasters",
    show: bool = True,
) -> folium.FeatureGroup:
    """Add disaster point features as an independently switchable map layer."""
    collection = validate_feature_collection(feature_collection)
    group = folium.FeatureGroup(name=name, show=show)
    for feature in collection["features"]:
        longitude, latitude = feature["geometry"]["coordinates"][:2]
        properties = feature.get("properties", {})
        disaster_type = str(properties.get("disaster_type", "Disaster"))
        status = str(properties.get("status", "reported"))
        folium.Marker(
            location=[latitude, longitude],
            tooltip=f"{disaster_type} | {status}",
            icon=folium.Icon(color="red", icon="warning-sign", prefix="glyphicon"),
        ).add_to(group)
    group.add_to(map_object)
    return group
