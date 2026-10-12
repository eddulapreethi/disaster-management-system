from __future__ import annotations

import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import geopandas as gpd
import requests

ROOT = Path(__file__).resolve().parent
GEO_ROOT = ROOT / "data" / "geographic_data"
KOCHI_BBOX = {"south": 9.8, "west": 76.0, "north": 10.1, "east": 76.5}
REQUEST_TIMEOUT_SECONDS = 120


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_bbox() -> tuple[float, float, float, float]:
    return (KOCHI_BBOX["west"], KOCHI_BBOX["south"], KOCHI_BBOX["east"], KOCHI_BBOX["north"])


def _ensure_gpkg() -> Path:
    gpkg_dir = GEO_ROOT / "southern-zone-latest-free"
    gpkg = gpkg_dir / "southern-zone.gpkg"
    if gpkg.exists():
        return gpkg
    zip_path = GEO_ROOT / "southern-zone-latest-free.gpkg.zip"
    if not zip_path.exists():
        raise FileNotFoundError(f"Missing source GeoPackage archive: {zip_path}")
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(gpkg_dir)
    if not gpkg.exists():
        raise FileNotFoundError(f"GeoPackage was not extracted to {gpkg}")
    return gpkg


def _export_layer(layer_name: str, output_name: str, *, filters: list[str] | None = None) -> dict[str, object]:
    gdf = gpd.read_file(_ensure_gpkg(), layer=layer_name, bbox=_read_bbox())
    if filters:
        gdf = gdf[gdf["fclass"].isin(filters)]
    if gdf.empty:
        raise ValueError(f"No real features found for {layer_name} in Kochi bbox.")
    out_path = GEO_ROOT / output_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path, driver="GeoJSON")
    return {
        "layer": layer_name,
        "path": str(out_path),
        "rows": int(len(gdf)),
        "crs": str(gdf.crs),
        "geometry_types": gdf.geom_type.value_counts().to_dict(),
        "source": "https://download.geofabrik.de/asia/india.html",
        "license": "OpenStreetMap © OpenStreetMap contributors, ODbL 1.0",
        "fetched_at": iso_now(),
    }


def download_watershed_boundaries() -> dict[str, object]:
    ws_dir = GEO_ROOT / "watersheds"
    ws_dir.mkdir(parents=True, exist_ok=True)
    zip_url = "https://data.hydrosheds.org/file/hydrobasins/standard/hybas_as_lev06_v1c.zip"
    zip_path = ws_dir / "hybas_as_lev06_v1c.zip"
    response = requests.get(zip_url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    zip_path.write_bytes(response.content)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(ws_dir)
    shp_candidates = sorted(ws_dir.glob("**/*.shp"))
    if not shp_candidates:
        raise FileNotFoundError("HydroSHEDS archive did not contain a shapefile.")
    shp_path = shp_candidates[0]
    try:
        gdf = gpd.read_file(str(shp_path), bbox=_read_bbox())
    except Exception:
        import shapefile
        rebuilt = shp_path.with_name(f"{shp_path.stem}_fixed")
        reader = shapefile.Reader(str(shp_path))
        writer = shapefile.Writer(str(rebuilt), shapeType=reader.shapeType)
        writer.fields = list(reader.fields)
        for index in range(len(reader)):
            writer.record(*reader.record(index))
            writer.shape(reader.shape(index))
        writer.close()
        gdf = gpd.read_file(str(rebuilt.with_suffix(".shp")), bbox=_read_bbox())
    if gdf.empty:
        raise ValueError("HydroSHEDS returned no watersheds for the Kochi study area.")
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    out_path = ws_dir / "kochi_watersheds.geojson"
    gdf.to_file(out_path, driver="GeoJSON")
    return {
        "layer": "hydrobasins",
        "path": str(out_path),
        "rows": int(len(gdf)),
        "crs": str(gdf.crs),
        "geometry_types": gdf.geom_type.value_counts().to_dict(),
        "source": zip_url,
        "license": "HydroSHEDS public basin boundary dataset",
        "fetched_at": iso_now(),
    }


def download_dem() -> dict[str, object]:
    elevation_dir = GEO_ROOT / "elevation"
    elevation_dir.mkdir(parents=True, exist_ok=True)
    url = "https://portal.opentopography.org/API/globaldem"
    api_key = os.getenv("OPENTOPOGRAPHY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Set OPENTOPOGRAPHY_API_KEY in the local environment to download the DEM."
        )
    params = {
        "demtype": "SRTMGL1",
        "south": KOCHI_BBOX["south"],
        "north": KOCHI_BBOX["north"],
        "west": KOCHI_BBOX["west"],
        "east": KOCHI_BBOX["east"],
        "outputFormat": "GTiff",
        "API_Key": api_key,
    }
    target = elevation_dir / "kochi_dem.tif"
    with requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS, stream=True) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    handle.write(chunk)
    try:
        import rasterio
        with rasterio.open(target) as src:
            crs = src.crs
            bounds = src.bounds
            if src.width <= 0 or src.height <= 0:
                raise ValueError("Downloaded DEM raster has invalid dimensions.")
            if crs is None:
                raise ValueError("Downloaded DEM raster has no CRS.")
    except Exception as exc:  # pragma: no cover - runtime validation only
        raise ValueError(f"DEM validation failed: {exc}") from exc
    return {
        "path": str(target),
        "source": url + "?" + urlencode({key: value for key, value in params.items() if key != "API_Key"}),
        "license": (
            "Confirm the applicable OpenTopography and SRTMGL1 source-data terms before redistribution; "
            "no USGS 3DEP license is asserted."
        ),
        "fetched_at": iso_now(),
        "crs": str(crs),
        "bounds": [round(bounds.left, 6), round(bounds.bottom, 6), round(bounds.right, 6), round(bounds.top, 6)],
    }


def build_report() -> dict[str, object]:
    report: dict[str, object] = {
        "study_area": "Kochi, Kerala, India",
        "bbox": KOCHI_BBOX,
        "retrieval_date": iso_now(),
        "datasets": [],
    }

    datasets = [
        ("administrative_boundaries", "administrative_boundaries/kochi_administrative_boundaries.geojson", "gis_osm_adminareas_a_free", ["admin_level4", "admin_level5", "admin_level6"]),
        ("lakes", "lakes/kochi_lakes.geojson", "gis_osm_water_a_free", ["water", "wetland", "wetland_marsh", "wetland_mangrove", "wetland_swamp", "reservoir"]),
        ("land_use", "land_use/kochi_land_use.geojson", "gis_osm_landuse_a_free", None),
        ("rivers", "rivers/kochi_rivers.geojson", "gis_osm_waterways_free", ["river", "stream", "canal", "drain"]),
        ("roads", "roads/kochi_roads.geojson", "gis_osm_roads_free", None),
    ]
    for category, output_name, layer_name, filters in datasets:
        entry = _export_layer(layer_name, output_name, filters=filters)
        report["datasets"].append({"category": category, **entry})
    report["datasets"].append({"category": "elevation", **download_dem()})
    report["datasets"].append({"category": "watersheds", **download_watershed_boundaries()})
    return report


def main() -> None:
    GEO_ROOT.mkdir(parents=True, exist_ok=True)
    report = build_report()
    report_path = GEO_ROOT / "download_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": "ok", "report_path": str(report_path), "datasets": len(report["datasets"])}, indent=2))


if __name__ == "__main__":
    main()
