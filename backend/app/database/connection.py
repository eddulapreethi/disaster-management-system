import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./disasterguard.db")
database_url = make_url(DATABASE_URL)
if (
    database_url.drivername.startswith("sqlite")
    and database_url.database not in (None, "", ":memory:")
    and not database_url.database.startswith("file:")
    and not Path(database_url.database).is_absolute()
):
    backend_dir = Path(__file__).resolve().parents[2]
    database_url = database_url.set(
        database=str((backend_dir / database_url.database).resolve())
    )
DATABASE_URL = database_url.render_as_string(hide_password=False)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)


class Base(DeclarativeBase):
    pass