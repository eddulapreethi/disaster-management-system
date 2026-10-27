import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.database.database import _upgrade_sqlite_hydrology_schema, _upgrade_sqlite_resource_constraints


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
