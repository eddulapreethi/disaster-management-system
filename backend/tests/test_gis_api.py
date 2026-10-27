from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.gis import router
from app.services.gis_readiness_service import GEOGRAPHIC_LAYERS
from app.utils.authentication import get_current_user


def _client(authenticated: bool = True) -> TestClient:
    application = FastAPI()
    application.include_router(router)
    if authenticated:
        application.dependency_overrides[get_current_user] = lambda: object()
    return TestClient(application)


def test_geojson_layers_serve_only_allowlisted_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import app.api.gis as gis_api

    for layer_name, relative_path in GEOGRAPHIC_LAYERS.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'{{"layer":"{layer_name}"}}', encoding="utf-8")
    monkeypatch.setattr(gis_api, "GIS_DATA_ROOT", tmp_path)

    with _client() as client:
        for layer_name in GEOGRAPHIC_LAYERS:
            response = client.get(f"/gis/layers/{layer_name}")
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("application/geo+json")
            assert response.headers["cache-control"] == "private, max-age=300"
            assert response.json() == {"layer": layer_name}

        assert client.get("/gis/layers/not-allowlisted").status_code == 422


def test_geojson_layers_require_authentication() -> None:
    with _client(authenticated=False) as client:
        response = client.get("/gis/layers/rivers")

    assert response.status_code == 401


def test_missing_geojson_layer_returns_not_found(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import app.api.gis as gis_api

    monkeypatch.setattr(gis_api, "GIS_DATA_ROOT", tmp_path)
    with _client() as client:
        response = client.get("/gis/layers/rivers")

    assert response.status_code == 404
    assert response.json()["detail"] == "GIS layer is unavailable."


def test_allowlisted_layer_path_cannot_escape_geographic_data_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import app.api.gis as gis_api

    outside_file = tmp_path / "outside.geojson"
    outside_file.write_text('{"unexpected":true}', encoding="utf-8")
    monkeypatch.setattr(gis_api, "GIS_DATA_ROOT", tmp_path / "geographic_data")
    monkeypatch.setitem(GEOGRAPHIC_LAYERS, "rivers", "../outside.geojson")

    with _client() as client:
        response = client.get("/gis/layers/rivers")

    assert response.status_code == 404
    assert outside_file.read_text(encoding="utf-8") == '{"unexpected":true}'
