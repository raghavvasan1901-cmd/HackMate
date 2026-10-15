import logging
import os
import time

from app.database import Base, SessionLocal, engine, migrate_existing_sqlite_schema
from app.services.event_sync import configured_sources, sync_event_sources


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        interval = int(os.getenv("HACKMATE_SYNC_INTERVAL_SECONDS", "3600"))
        owner_id = int(os.environ["HACKMATE_SYNC_OWNER_USER_ID"])
    except (ValueError, KeyError) as exc:
        raise SystemExit(
            "Set HACKMATE_SYNC_INTERVAL_SECONDS to an integer and "
            "HACKMATE_SYNC_OWNER_USER_ID to an existing user ID."
        ) from exc
    if interval < 60:
        raise SystemExit("HACKMATE_SYNC_INTERVAL_SECONDS must be at least 60.")

    migrate_existing_sqlite_schema()
    Base.metadata.create_all(bind=engine)
    logger = logging.getLogger("hackmate.sync_worker")
    logger.info("HackMate event sync worker started; interval_seconds=%s", interval)
    while True:
        try:
            if configured_sources():
                with SessionLocal() as db:
                    sync_event_sources(db, owner_id)
            else:
                logger.info("No permitted iCalendar feeds configured; waiting for next interval.")
        except Exception as exc:
            logger.error("Event sync cycle failed (%s).", type(exc).__name__)
        time.sleep(interval)


if __name__ == "__main__":
    main()
