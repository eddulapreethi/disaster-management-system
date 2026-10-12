from sqlalchemy import create_engine, inspect, text

from app.database.database import _upgrade_sqlite_hydrology_schema


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
