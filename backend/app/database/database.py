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


def create_tables() -> None:
    # Import models so SQLAlchemy registers their tables before create_all.
    from app.models import (  # noqa: F401
        alert,
        disaster,
        hydrological_observation,
        hydrology_collection_state,
        prediction,
        resource,
        simulation,
        user,
        weather_observation,
    )

    Base.metadata.create_all(bind=engine)
    _upgrade_sqlite_weather_schema()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()