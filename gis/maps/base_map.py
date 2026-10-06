import folium


def create_base_map(
    center: tuple[float, float] = (22.5, 80.0),
    zoom_start: int = 5,
    *,
    tiles: str = "OpenStreetMap",
) -> folium.Map:
    """Create a Leaflet map; center is passed as (latitude, longitude)."""
    latitude, longitude = center
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Map center must be a valid (latitude, longitude) pair.")
    if not 0 <= zoom_start <= 18:
        raise ValueError("zoom_start must be between 0 and 18.")
    return folium.Map(
        location=[latitude, longitude],
        zoom_start=zoom_start,
        tiles=tiles,
        control_scale=True,
        prefer_canvas=True,
    )
