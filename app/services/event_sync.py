import hashlib
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

import httpx
from icalendar import Calendar
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    EventSourceListing,
    EventSyncLock,
    EventSyncRun,
    EventSyncSource,
    HackathonEvent,
    User,
    now_utc,
)


logger = logging.getLogger(__name__)
_SYNC_LOCK_ID = 1
_SYNC_LOCK_DURATION = timedelta(minutes=15)
_PROCESS_LOCK = threading.Lock()
_SOURCE_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{1,80}$")
_SCOPES = {
    "campus", "local", "state", "national", "international", "online_global", "unknown",
}


@dataclass(frozen=True)
class FeedConfig:
    key: str
    name: str
    url: str


@dataclass(frozen=True)
class NormalizedEvent:
    source_event_id: str
    name: str
    organizer: str
    description: str
    starts_at: datetime
    ends_at: datetime
    event_url: str
    registration_url: str = ""
    registration_opens_at: datetime | None = None
    registration_deadline: datetime | None = None
    event_format: str = ""
    location: str = ""
    country: str = ""
    region: str = ""
    scope: str = ""
    eligibility: str = ""
    team_size_min: int | None = None
    team_size_max: int | None = None
    tags: tuple[str, ...] = ()
    prize_details: str = ""
    status: str = "scheduled"
    source_updated_at: datetime | None = None

    @property
    def completeness(self) -> int:
        fields = (
            self.organizer, self.description, self.event_url, self.registration_url,
            self.location, self.country, self.region, self.scope, self.eligibility,
            self.event_format, self.tags, self.prize_details, self.registration_deadline,
        )
        return round(sum(bool(value) for value in fields) * 100 / len(fields))


class EventSourceAdapter:
    """Interface for permitted structured event sources; never fetches web pages to scrape."""

    def __init__(self, source: FeedConfig):
        self.source = source

    def fetch(self, client: httpx.Client) -> tuple[list[NormalizedEvent], int]:
        raise NotImplementedError


def configured_sources() -> list[FeedConfig]:
    raw = os.getenv("HACKMATE_ICAL_FEEDS", "[]")
    try:
        records = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("HACKMATE_ICAL_FEEDS must be a JSON array") from exc
    if not isinstance(records, list) or len(records) > 10:
        raise ValueError("HACKMATE_ICAL_FEEDS must contain at most 10 feed objects")
    feeds = []
    seen_keys: set[str] = set()
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("Each iCalendar feed must be an object")
        key, name, url = item.get("key"), item.get("name"), item.get("url")
        if not isinstance(key, str) or not _SOURCE_KEY_PATTERN.fullmatch(key):
            raise ValueError("Each feed requires a safe, unique key")
        if key in seen_keys:
            raise ValueError("iCalendar feed keys must be unique")
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError("Each feed requires a display name of at most 120 characters")
        if not isinstance(url, str) or len(url) > 2000:
            raise ValueError("Each feed requires a valid HTTPS URL")
        parsed_url = urlparse(url)
        if parsed_url.scheme != "https" or not parsed_url.hostname or parsed_url.username or parsed_url.password:
            raise ValueError("iCalendar feed URLs must use HTTPS without embedded credentials")
        seen_keys.add(key)
        feeds.append(FeedConfig(key=key, name=name.strip(), url=url))
    return feeds


def _ical_datetime(value: Any, *, exclusive_date_end: bool = False) -> datetime:
    if isinstance(value, date) and not isinstance(value, datetime):
        parsed = datetime.combine(value, datetime_time.min, tzinfo=timezone.utc)
        if exclusive_date_end:
            parsed -= timedelta(seconds=1)
        return parsed
    if not isinstance(value, datetime):
        raise ValueError("VEVENT date is missing or invalid")
    if value.tzinfo is None:
        raise ValueError("VEVENT date-time must include a timezone")
    return value.astimezone(timezone.utc)


def _ical_optional_datetime(component: Any, key: str) -> datetime:
    value = component.decoded(key)
    if isinstance(value, (date, datetime)):
        return _ical_datetime(value)
    if isinstance(value, bytes):
        value = value.decode("ascii")
    if not isinstance(value, str):
        raise ValueError(f"{key} is not a valid iCalendar date")
    value = value.strip()
    for date_format in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            parsed = datetime.strptime(value, date_format)
            if date_format.endswith("Z"):
                parsed = parsed.replace(tzinfo=timezone.utc)
            elif date_format == "%Y%m%dT%H%M%S":
                timezone_name = component.get(key).params.get("TZID")
                if not timezone_name:
                    raise ValueError(f"{key} date-time must include a timezone")
                parsed = parsed.replace(tzinfo=ZoneInfo(str(timezone_name)))
            else:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    try:
        return _ical_datetime(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as exc:
        raise ValueError(f"{key} is not a valid iCalendar date") from exc


def _property_text(component: Any, key: str) -> str:
    value = component.get(key)
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _safe_external_url(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        return ""
    return value[:500]


def _optional_integer(component: Any, key: str) -> int | None:
    value = _property_text(component, key)
    if not value:
        return None
    parsed = int(value)
    if parsed < 1 or parsed > 100:
        raise ValueError(f"{key} is outside the supported range")
    return parsed


def _parse_ical_event(component: Any) -> NormalizedEvent:
    name = _property_text(component, "SUMMARY")
    source_id = _property_text(component, "UID")
    if not name or not source_id:
        raise ValueError("VEVENT requires both SUMMARY and UID")
    starts_at = _ical_datetime(component.decoded("DTSTART"))
    raw_end = component.get("DTEND")
    if raw_end is None:
        duration = component.get("DURATION")
        if duration is None:
            raise ValueError("VEVENT requires DTEND or DURATION")
        ends_at = starts_at + duration.dt
    else:
        ends_at = _ical_datetime(component.decoded("DTEND"), exclusive_date_end=True)
    if ends_at <= starts_at:
        raise ValueError("VEVENT end precedes its start")
    opens_at = (
        _ical_optional_datetime(component, "X-REGISTRATION-START")
        if component.get("X-REGISTRATION-START") else None
    )
    deadline = (
        _ical_optional_datetime(component, "X-REGISTRATION-DEADLINE")
        if component.get("X-REGISTRATION-DEADLINE") else None
    )
    if deadline is not None and deadline >= starts_at:
        raise ValueError("Registration deadline must be before event start")
    if opens_at is not None and deadline is not None and opens_at > deadline:
        raise ValueError("Registration opening date is after the deadline")

    status = _property_text(component, "STATUS").lower()
    event_status = "cancelled" if status == "cancelled" else "scheduled"
    event_url = _safe_external_url(_property_text(component, "URL"))
    registration_url = _safe_external_url(_property_text(component, "X-REGISTRATION-URL"))
    event_format = _property_text(component, "X-EVENT-FORMAT").lower()
    if event_format not in {"online", "offline", "hybrid"}:
        event_format = ""
    scope = _property_text(component, "X-HACKMATE-SCOPE").lower().replace("-", "_")
    if scope not in _SCOPES:
        scope = ""
    organizer = _property_text(component, "ORGANIZER")
    if organizer.startswith("mailto:"):
        organizer = organizer[7:]
    categories = component.get("CATEGORIES")
    tags = tuple(str(value).strip() for value in getattr(categories, "cats", []) if str(value).strip())

    return NormalizedEvent(
        source_event_id=source_id[:255],
        name=name[:160],
        organizer=organizer[:160],
        description=_property_text(component, "DESCRIPTION")[:5000],
        starts_at=starts_at,
        ends_at=ends_at,
        event_url=event_url[:500],
        registration_url=registration_url[:500],
        registration_opens_at=opens_at,
        registration_deadline=deadline,
        event_format=event_format,
        location=_property_text(component, "LOCATION")[:200],
        country=_property_text(component, "X-COUNTRY")[:100],
        region=_property_text(component, "X-REGION")[:100],
        scope=scope,
        eligibility=_property_text(component, "X-ELIGIBILITY")[:500],
        tags=tags[:30],
        prize_details=_property_text(component, "X-PRIZE-DETAILS")[:3000],
        team_size_min=_optional_integer(component, "X-MIN-TEAM-SIZE"),
        team_size_max=_optional_integer(component, "X-MAX-TEAM-SIZE"),
        status=event_status,
        source_updated_at=(
            _ical_datetime(component.decoded("LAST-MODIFIED"))
            if component.get("LAST-MODIFIED") else None
        ),
    )


def parse_icalendar(payload: bytes) -> tuple[list[NormalizedEvent], int]:
    calendar = Calendar.from_ical(payload)
    events = []
    invalid_count = 0
    for component in calendar.walk("VEVENT"):
        try:
            events.append(_parse_ical_event(component))
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            invalid_count += 1
    return events, invalid_count


class ICalendarFeedAdapter(EventSourceAdapter):
    def fetch(self, client: httpx.Client) -> tuple[list[NormalizedEvent], int]:
        response = _request_with_retries(client, self.source.url)
        if response.status_code == 304:
            return [], 0
        if "text/calendar" not in response.headers.get("content-type", "").lower() and not response.content.lstrip().startswith(b"BEGIN:VCALENDAR"):
            raise ValueError("Configured source did not return an iCalendar feed")
        return parse_icalendar(response.content)


def _request_with_retries(client: httpx.Client, url: str) -> httpx.Response:
    for attempt in range(3):
        try:
            response = client.get(url, headers={"Accept": "text/calendar", "User-Agent": "HackMate-event-sync/1.0"})
            if response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
                return response
            if attempt == 2:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After", "")
            try:
                delay = min(10.0, max(0.0, float(retry_after)))
            except ValueError:
                delay = 0.25 * (2 ** attempt)
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == 2:
                raise
            delay = 0.25 * (2 ** attempt)
        time.sleep(delay)
    raise RuntimeError("Feed request failed after retries")


def _claim_sync_lock(db: Session) -> bool:
    if db.get(EventSyncLock, _SYNC_LOCK_ID) is None:
        try:
            db.add(EventSyncLock(id=_SYNC_LOCK_ID))
            db.commit()
        except IntegrityError:
            db.rollback()
    now = now_utc()
    claimed = db.execute(
        update(EventSyncLock)
        .where(
            EventSyncLock.id == _SYNC_LOCK_ID,
            or_(EventSyncLock.locked_until.is_(None), EventSyncLock.locked_until < now),
        )
        .values(locked_until=now + _SYNC_LOCK_DURATION)
    )
    db.commit()
    return claimed.rowcount == 1


def _release_sync_lock(db: Session) -> None:
    db.execute(
        update(EventSyncLock).where(EventSyncLock.id == _SYNC_LOCK_ID).values(locked_until=None)
    )
    db.commit()


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _canonical_url(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    query = [
        (key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
    ]
    return urlunparse((
        parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path.rstrip("/"),
        parsed.params, urlencode(query), "",
    ))


def _find_duplicate(db: Session, source: FeedConfig, item: NormalizedEvent) -> HackathonEvent | None:
    if item.event_url:
        canonical_url = _canonical_url(item.event_url)
        events = db.scalars(
            select(HackathonEvent).where(HackathonEvent.event_url != "").limit(500)
        ).all()
        for existing in events:
            if _canonical_url(existing.event_url) == canonical_url:
                return existing
    if not item.organizer:
        return None
    same_day = db.scalars(
        select(HackathonEvent).where(
            func.date(HackathonEvent.starts_at) == item.starts_at.date().isoformat(),
            func.lower(HackathonEvent.organizer) == _normalized(item.organizer),
        ).limit(50)
    ).all()
    title = _normalized(item.name)
    return next((event for event in same_day if _normalized(event.name) == title), None)


def _apply_source_event(event: HackathonEvent, source: FeedConfig, item: NormalizedEvent, fetched_at: datetime) -> None:
    event.is_imported = True
    event.source_name = event.source_name or source.name
    event.name = item.name
    event.organizer = item.organizer or event.organizer
    event.description = item.description or event.description
    event.starts_at = item.starts_at
    event.ends_at = item.ends_at
    event.registration_deadline = item.registration_deadline
    event.registration_opens_at = item.registration_opens_at
    event.location = item.location or event.location
    event.event_url = item.event_url or event.event_url
    event.registration_url = item.registration_url or event.registration_url
    event.eligibility = item.eligibility or event.eligibility
    event.tags = ",".join(item.tags) if item.tags else event.tags
    event.event_format = item.event_format or event.event_format
    event.country = item.country or event.country
    event.region = item.region or event.region
    event.scope = item.scope or event.scope
    event.team_size_min = item.team_size_min if item.team_size_min is not None else event.team_size_min
    event.team_size_max = item.team_size_max if item.team_size_max is not None else event.team_size_max
    event.prize_details = item.prize_details or event.prize_details
    event.event_status = (
        "expired" if item.status == "scheduled" and item.ends_at < now_utc() else item.status
    )
    event.source_confidence = None
    event.source_completeness = item.completeness
    event.source_updated_at = item.source_updated_at
    event.last_fetched_at = fetched_at


def _upsert_source_event(
    db: Session, owner_id: int, source: FeedConfig, item: NormalizedEvent, fetched_at: datetime,
) -> str:
    listing = db.scalar(
        select(EventSourceListing).where(
            EventSourceListing.source_key == source.key,
            EventSourceListing.source_event_id == item.source_event_id,
        )
    )
    event = db.get(HackathonEvent, listing.event_id) if listing else None
    if event is None:
        event = _find_duplicate(db, source, item)
    change = "updated"
    if event is None:
        event = HackathonEvent(
            creator_id=owner_id,
            name=item.name,
            organizer=item.organizer,
            description=item.description,
            starts_at=item.starts_at,
            ends_at=item.ends_at,
            registration_deadline=item.registration_deadline,
            location=item.location,
            event_url=item.event_url,
            eligibility=item.eligibility,
            tags=",".join(item.tags),
            event_status=item.status,
        )
        db.add(event)
        db.flush()
        change = "created"
    if event.is_imported or not event.source_name:
        _apply_source_event(event, source, item, fetched_at)
    if listing is None:
        listing = EventSourceListing(
            event_id=event.id,
            source_key=source.key,
            source_name=source.name,
            source_event_id=item.source_event_id,
            listing_url=item.event_url,
            last_fetched_at=fetched_at,
        )
        db.add(listing)
    else:
        listing.last_fetched_at = fetched_at
        listing.listing_url = item.event_url or listing.listing_url
    db.flush()
    return change


def sync_event_sources(db: Session, owner_id: int, client: httpx.Client | None = None) -> dict[str, Any]:
    if not _PROCESS_LOCK.acquire(blocking=False):
        return {"status": "already_running", "sources": [], "events_found": 0, "events_created": 0, "events_updated": 0}
    owns_client = client is None
    http_client = client or httpx.Client(timeout=httpx.Timeout(12.0, connect=5.0), follow_redirects=False)
    run: EventSyncRun | None = None
    lock_claimed = False
    try:
        try:
            sources = configured_sources()
        except ValueError:
            logger.warning("Event feed configuration is invalid")
            raise
        if db.get(User, owner_id) is None:
            raise ValueError("A valid event sync owner user is required")
        if not _claim_sync_lock(db):
            return {"status": "already_running", "sources": [], "events_found": 0, "events_created": 0, "events_updated": 0}
        lock_claimed = True
        run = EventSyncRun(source_count=len(sources))
        db.add(run)
        db.commit()
        result: dict[str, Any] = {
            "status": "success" if sources else "no_sources", "sources": [], "events_found": 0,
            "events_created": 0, "events_updated": 0, "invalid_events": 0,
        }
        for source in sources:
            state = db.scalar(select(EventSyncSource).where(EventSyncSource.source_key == source.key))
            if state is None:
                state = EventSyncSource(source_key=source.key, source_name=source.name)
                db.add(state)
                db.commit()
            state.source_name = source.name
            state.last_attempt_at = now_utc()
            try:
                found, invalid_count = ICalendarFeedAdapter(source).fetch(http_client)
                created = updated = 0
                fetched_at = now_utc()
                for item in found:
                    try:
                        change = _upsert_source_event(db, owner_id, source, item, fetched_at)
                        db.commit()
                    except IntegrityError:
                        db.rollback()
                        existing = db.scalar(
                            select(EventSourceListing).where(
                                EventSourceListing.source_key == source.key,
                                EventSourceListing.source_event_id == item.source_event_id,
                            )
                        )
                        if existing is None:
                            raise
                        current_event = db.get(HackathonEvent, existing.event_id)
                        if current_event is not None and current_event.is_imported:
                            _apply_source_event(current_event, source, item, fetched_at)
                            existing.last_fetched_at = fetched_at
                            db.commit()
                            change = "updated"
                        else:
                            continue
                    if change == "created":
                        created += 1
                    else:
                        updated += 1
                state = db.scalar(select(EventSyncSource).where(EventSyncSource.source_key == source.key))
                state.last_success_at = fetched_at
                state.last_error = ""
                state.last_found = len(found)
                state.last_created = created
                state.last_updated = updated
                db.commit()
                source_result = {
                    "key": source.key, "name": source.name, "status": "success",
                    "events_found": len(found), "events_created": created,
                    "events_updated": updated, "invalid_events": invalid_count,
                }
                result["events_found"] += len(found)
                result["events_created"] += created
                result["events_updated"] += updated
                result["invalid_events"] += invalid_count
            except (httpx.HTTPError, ValueError, RuntimeError, OSError, SQLAlchemyError) as exc:
                db.rollback()
                state = db.scalar(select(EventSyncSource).where(EventSyncSource.source_key == source.key))
                if state is None:
                    state = EventSyncSource(source_key=source.key, source_name=source.name)
                    db.add(state)
                state.last_attempt_at = now_utc()
                state.last_error = f"Source unavailable or invalid feed ({type(exc).__name__})"
                db.commit()
                logger.warning("Hackathon feed sync failed", extra={
                    "source_key": source.key, "error_type": type(exc).__name__,
                })
                source_result = {
                    "key": source.key, "name": source.name, "status": "failed",
                    "error": state.last_error, "events_found": 0,
                    "events_created": 0, "events_updated": 0,
                }
                result["status"] = "partial_failure"
            result["sources"].append(source_result)
        run.finished_at = now_utc()
        run.status = result["status"] if sources else "no_sources"
        run.events_found = result["events_found"]
        run.events_created = result["events_created"]
        run.events_updated = result["events_updated"]
        run.failure_count = sum(item["status"] == "failed" for item in result["sources"])
        run.summary = (
            f"{len(result['sources'])} configured feeds; {result['events_found']} events found; "
            f"{result['events_created']} created; {result['events_updated']} updated; "
            f"{result['invalid_events']} invalid records."
        )
        db.commit()
        logger.info("Hackathon feed sync completed", extra={
            "status": run.status, "source_count": run.source_count,
            "events_found": run.events_found, "events_created": run.events_created,
            "events_updated": run.events_updated, "failure_count": run.failure_count,
        })
        return result
    finally:
        if lock_claimed:
            _release_sync_lock(db)
        if owns_client:
            http_client.close()
        _PROCESS_LOCK.release()


def source_key_fingerprint(url: str) -> str:
    """Stable diagnostic fingerprint; never return or log the configured URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:12]
