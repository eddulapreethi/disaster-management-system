from collections.abc import Generator
import logging

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.database.connection import Base, engine

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
logger = logging.getLogger(__name__)


def _upgrade_sqlite_weather_schema(bind=engine) -> None:
    if bind.dialect.name != "sqlite" or not inspect(bind).has_table("weather_observations"):
        return

    with bind.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("weather_observations")}
        if "source" not in columns:
            connection.execute(
                text("ALTER TABLE weather_observations ADD COLUMN source VARCHAR(64) NOT NULL DEFAULT 'open-meteo'")
            )
        if "created_at" not in columns:
            connection.execute(text("ALTER TABLE weather_observations ADD COLUMN created_at DATETIME"))
            connection.execute(
                text("UPDATE weather_observations SET created_at = COALESCE(fetched_at, CURRENT_TIMESTAMP)")
            )

        duplicate_groups = connection.execute(
            text(
                "SELECT COUNT(*) FROM ("
                "SELECT station_id, observation_time, source FROM weather_observations "
                "GROUP BY station_id, observation_time, source HAVING COUNT(*) > 1)"
            )
        ).scalar_one()
        if duplicate_groups:
            logger.warning(
                "Preserved %s duplicate weather observation groups in the existing SQLite database; "
                "the collector will skip existing keys and no unique index was added.",
                duplicate_groups,
            )
            return

        schema_inspector = inspect(connection)
        unique_key_index_exists = any(
            index["unique"] and index["column_names"] == ["station_id", "observation_time", "source"]
            for index in schema_inspector.get_indexes("weather_observations")
        ) or any(
            constraint["column_names"] == ["station_id", "observation_time", "source"]
            for constraint in schema_inspector.get_unique_constraints("weather_observations")
        )
        if not unique_key_index_exists:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_weather_station_source_time "
                    "ON weather_observations (station_id, observation_time, source)"
                )
            )


def _upgrade_sqlite_hydrology_schema(bind=engine) -> None:
    if bind.dialect.name != "sqlite" or not inspect(bind).has_table("hydrology_collection_state"):
        return

    additions = {
        "records_returned": "INTEGER NOT NULL DEFAULT 0",
        "valid_records": "INTEGER NOT NULL DEFAULT 0",
        "newer_observation_found": "BOOLEAN NOT NULL DEFAULT 0",
        "last_error": "TEXT",
    }
    with bind.begin() as connection:
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("hydrology_collection_state")
        }
        for name, sql_type in additions.items():
            if name not in columns:
                connection.execute(
                    text(f"ALTER TABLE hydrology_collection_state ADD COLUMN {name} {sql_type}")
                )


def _upgrade_sqlite_provider_metadata_schema(bind=engine) -> None:
    if bind.dialect.name != "sqlite":
        return

    with bind.begin() as connection:
        for table_name in ("weather_observations", "hydrological_observations"):
            if not inspect(connection).has_table(table_name):
                continue
            columns = {
                column["name"]
                for column in inspect(connection).get_columns(table_name)
            }
            if "provider_metadata" not in columns:
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        "ADD COLUMN provider_metadata JSON NOT NULL DEFAULT '{}'"
                    )
                )


def _upgrade_sqlite_resource_constraints(bind=engine) -> None:
    if bind.dialect.name != "sqlite" or not inspect(bind).has_table("resources"):
        return

    with bind.begin() as connection:
        for operation, event in (("insert", "INSERT"), ("update", "UPDATE")):
            connection.execute(
                text(
                    f"CREATE TRIGGER IF NOT EXISTS trg_resources_validate_{operation} "
                    f"BEFORE {event} ON resources "
                    "WHEN NEW.quantity IS NULL OR NEW.quantity < 0 "
                    "OR NEW.latitude IS NULL OR NEW.latitude NOT BETWEEN -90 AND 90 "
                    "OR NEW.longitude IS NULL OR NEW.longitude NOT BETWEEN -180 AND 180 "
                    "BEGIN SELECT RAISE(ABORT, 'Resource quantity or coordinates are invalid'); END"
                )
            )


def _upgrade_sqlite_incident_schema(bind=engine) -> None:
    if bind.dialect.name != "sqlite":
        return

    with bind.begin() as connection:
        inspector = inspect(connection)
        if inspector.has_table("users"):
            columns = {column["name"] for column in inspector.get_columns("users")}
            if "role" not in columns:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'")
                )

        if not inspector.has_table("disasters"):
            return
        columns = {column["name"] for column in inspector.get_columns("disasters")}
        additions = {
            "user_id": "INTEGER REFERENCES users(id)",
            "incident_time": "DATETIME",
            "incident_timezone": "VARCHAR(64)",
            "source": "VARCHAR(64) NOT NULL DEFAULT 'community_report'",
            "source_metadata": "JSON NOT NULL DEFAULT '{}'",
            "evidence_metadata": "JSON NOT NULL DEFAULT '[]'",
            "submitted_at": "DATETIME",
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(
                    text(f"ALTER TABLE disasters ADD COLUMN {name} {definition}")
                )
        if "created_at" in columns or "created_at" in additions:
            connection.execute(
                text("UPDATE disasters SET submitted_at = created_at WHERE submitted_at IS NULL")
            )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_disasters_user_id ON disasters (user_id)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_disasters_status_time ON disasters (status, incident_time)")
        )


def create_tables() -> None:
    # Import models so SQLAlchemy registers their tables before create_all.
    from app.models import (  # noqa: F401
        alert,
        disaster,
        hydrological_observation,
        hydrology_collection_state,
        prediction,
        disaster_review,
        resource,
        simulation,
        user,
        weather_observation,
    )

    Base.metadata.create_all(bind=engine)
    _upgrade_sqlite_provider_metadata_schema()
    _upgrade_sqlite_weather_schema()
    _upgrade_sqlite_hydrology_schema()
    _upgrade_sqlite_resource_constraints()
    _upgrade_sqlite_incident_schema()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()