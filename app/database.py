import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)
DATABASE_URL = os.getenv("HACKMATE_DATABASE_URL", "sqlite:///./hackmate.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)


if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_existing_sqlite_schema(migration_engine: Engine = engine) -> None:
    if migration_engine.dialect.name != "sqlite":
        return
    additions = {
        "reviews": {
            "communication_rating": "INTEGER",
            "reliability_rating": "INTEGER",
            "teamwork_rating": "INTEGER",
        },
        "developer_profiles": {
            "location_visible": "BOOLEAN NOT NULL DEFAULT 0",
            "education_visible": "BOOLEAN NOT NULL DEFAULT 1",
        },
        "hackathon_events": {
            "registration_url": "VARCHAR(500) NOT NULL DEFAULT ''",
            "event_format": "VARCHAR(20) NOT NULL DEFAULT ''",
            "country": "VARCHAR(100) NOT NULL DEFAULT ''",
            "region": "VARCHAR(100) NOT NULL DEFAULT ''",
            "scope": "VARCHAR(30) NOT NULL DEFAULT ''",
            "registration_opens_at": "DATETIME",
            "team_size_min": "INTEGER",
            "team_size_max": "INTEGER",
            "prize_details": "TEXT NOT NULL DEFAULT ''",
            "event_status": "VARCHAR(20) NOT NULL DEFAULT 'scheduled'",
            "is_imported": "BOOLEAN NOT NULL DEFAULT 0",
            "source_name": "VARCHAR(80) NOT NULL DEFAULT ''",
            "source_confidence": "FLOAT",
            "source_completeness": "INTEGER",
            "source_updated_at": "DATETIME",
            "last_fetched_at": "DATETIME",
        },
    }
    with migration_engine.begin() as connection:
        for table, columns in additions.items():
            table_exists = connection.exec_driver_sql(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).first()
            if table_exists is None:
                continue
            existing = {
                row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            }
            for column, definition in columns.items():
                if column not in existing:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                    )
