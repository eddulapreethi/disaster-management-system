from pathlib import Path
from typing import Any

import folium
from branca.element import Element

RISK_COLORS = {
    "low": "#21865b",
    "moderate": "#d69e20",
    "medium": "#d69e20",
    "high": "#c43d3d",
    "critical": "#7b1e32",
    "unknown": "#68737d",
}


def risk_color(risk_level: Any) -> str:
    """Get a stable color for a risk-level value."""
    return RISK_COLORS.get(str(risk_level).strip().lower(), RISK_COLORS["unknown"])


def add_risk_legend(map_object: folium.Map) -> None:
    """Add a compact fixed legend for the risk colors used by map layers."""
    entries = (("Low", "low"), ("Moderate", "moderate"), ("High", "high"), ("Critical", "critical"))
    rows = "".join(
        f'<div style="display:flex;align-items:center;gap:7px;margin:4px 0;">'
        f'<span style="width:11px;height:11px;border-radius:50%;background:{risk_color(key)};display:inline-block"></span>{label}</div>'
        for label, key in entries
    )
    legend_html = (
        '<div style="position:fixed;bottom:28px;left:18px;z-index:9999;background:#fff;'
        'padding:9px 12px;border:1px solid #aab2b8;border-radius:4px;'
        'font:12px/1.25 sans-serif;color:#20272b;box-shadow:0 1px 4px #0003">'
        f'<strong>Risk level</strong>{rows}</div>'
    )
    map_object.get_root().html.add_child(Element(legend_html))


def save_map(map_object: folium.Map, output_path: str | Path) -> Path:
    """Save a Folium map as standalone HTML and return the destination."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    map_object.save(str(destination))
    return destination
