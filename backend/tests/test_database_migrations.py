import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.database.database import (
    _upgrade_sqlite_incident_schema,
    _upgrade_sqlite_hydrology_schema,
    _upgrade_sqlite_provider_metadata_schema,
    _upgrade_sqlite_resource_constraints,
)


def test_sqlite_provider_metadata_upgrade_preserves_existing_observations() -> None:
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE weather_observations "
                    "(id INTEGER PRIMARY KEY, source VARCHAR(64) NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE hydrological_observations "
                    "(id INTEGER PRIMARY KEY, source VARCHAR(120) NOT NULL)"
                )
            )
            connection.execute(text("INSERT INTO weather_observations VALUES (1, 'open-meteo')"))
            connection.execute(text("INSERT INTO hydrological_observations VALUES (2, 'nwdp:test')"))

        _upgrade_sqlite_provider_metadata_schema(engine)
        _upgrade_sqlite_provider_metadata_schema(engine)

        with engine.connect() as connection:
            weather = connection.execute(
                text("SELECT id, source, provider_metadata FROM weather_observations")
            ).one()
            hydrology = connection.execute(
                text("SELECT id, source, provider_metadata FROM hydrological_observations")
            ).one()

        assert weather == (1, "open-meteo", "{}")
        assert hydrology == (2, "nwdp:test", "{}")
    finally:
        engine.dispose()


def test_sqlite_hydrology_upgrade_adds_diagnostics_without_deleting_state() -> None:
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE hydrology_collection_state ("
                    "source VARCHAR(128) PRIMARY KEY, "
                    "status VARCHAR(32) NOT NULL, "
                    "records_received INTEGER NOT NULL DEFAULT 0)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO hydrology_collection_state "
                    "(source, status, records_received) VALUES ('nwdp:test', 'READY', 7)"
                )
            )

        _upgrade_sqlite_hydrology_schema(engine)

        with engine.connect() as connection:
            columns = {column["name"] for column in inspect(connection).get_columns("hydrology_collection_state")}
            row = connection.execute(
                text(
                    "SELECT source, status, records_received, records_returned, valid_records, "
                    "newer_observation_found, last_error FROM hydrology_collection_state"
                )
            ).one()

        assert {
            "records_returned",
            "valid_records",
            "newer_observation_found",
            "last_error",
        } <= columns
        assert row == ("nwdp:test", "READY", 7, 0, 0, 0, None)
    finally:
        engine.dispose()


def test_sqlite_resource_upgrade_rejects_invalid_writes_and_preserves_existing_rows() -> None:
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE resources ("
                    "id INTEGER PRIMARY KEY, name TEXT NOT NULL, resource_type TEXT NOT NULL, "
                    "quantity INTEGER NOT NULL, unit TEXT NOT NULL, latitude FLOAT NOT NULL, "
                    "longitude FLOAT NOT NULL, status TEXT NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO resources VALUES "
                    "(1, 'Depot', 'water', 5, 'litres', 10, 76, 'available')"
                )
            )

        _upgrade_sqlite_resource_constraints(engine)
        _upgrade_sqlite_resource_constraints(engine)

        with engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM resources")).scalar_one() == 1
        values_to_reject = (
            (2, "Bad latitude", "water", 1, "litres", 91, 76, "available"),
            (3, "Bad quantity", "water", -1, "litres", 10, 76, "available"),
        )
        for values in values_to_reject:
            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "INSERT INTO resources "
                            "(id, name, resource_type, quantity, unit, latitude, longitude, status) "
                            "VALUES (:id, :name, :resource_type, :quantity, :unit, :latitude, :longitude, :status)"
                        ),
                        dict(zip(("id", "name", "resource_type", "quantity", "unit", "latitude", "longitude", "status"), values, strict=True)),
                    )
    finally:
        engine.dispose()


def test_sqlite_incident_upgrade_preserves_legacy_rows_and_adds_private_owner_fields() -> None:
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                    "email TEXT NOT NULL, hashed_password TEXT NOT NULL, created_at DATETIME NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE disasters (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                    "disaster_type VARCHAR(40) NOT NULL, description TEXT NOT NULL, latitude FLOAT NOT NULL, "
                    "longitude FLOAT NOT NULL, status VARCHAR(30) NOT NULL, created_at DATETIME NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO users VALUES (1, 'Legacy User', 'legacy@example.test', 'hash', "
                    "'2026-01-01 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO disasters VALUES (1, 'Legacy report', 'flood', 'old unowned report', "
                    "9.9, 76.2, 'reported', '2026-01-02 03:04:05')"
                )
            )

        _upgrade_sqlite_incident_schema(engine)
        _upgrade_sqlite_incident_schema(engine)

        with engine.connect() as connection:
            user_columns = {column["name"] for column in inspect(connection).get_columns("users")}
            disaster_columns = {column["name"] for column in inspect(connection).get_columns("disasters")}
            user = connection.execute(text("SELECT role FROM users WHERE id = 1")).scalar_one()
            report = connection.execute(
                text(
                    "SELECT user_id, status, submitted_at, source, source_metadata, evidence_metadata "
                    "FROM disasters WHERE id = 1"
                )
            ).one()

        assert "role" in user_columns
        assert {
            "user_id",
            "incident_time",
            "incident_timezone",
            "source",
            "source_metadata",
            "evidence_metadata",
            "submitted_at",
        } <= disaster_columns
        assert user == "user"
        assert report == (
            None,
            "reported",
            "2026-01-02 03:04:05",
            "community_report",
            "{}",
            "[]",
        )
    finally:
        engine.dispose()
