from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    DeveloperSkill, EventSourceListing, HackathonEvent, HackathonRegistration, Opportunity, User, UserInterest,
    UserSkill, now_utc,
)
from app.schemas import HackathonEventIn
from app.security import current_user, optional_user
from app.services.common import csv_list, split_list


router = APIRouter(tags=["Hackathon calendar"])


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _event_data(event: HackathonEvent, viewer_id: int | None, db: Session) -> dict:
    joined = False
    if viewer_id is not None:
        joined = db.scalar(
            select(HackathonRegistration.id).where(
                HackathonRegistration.event_id == event.id,
                HackathonRegistration.user_id == viewer_id,
            )
        ) is not None
    start = _as_utc(event.starts_at)
    end = _as_utc(event.ends_at)
    deadline = _as_utc(event.registration_deadline)
    current = now_utc()
    source_listings = db.scalars(
        select(EventSourceListing).where(EventSourceListing.event_id == event.id)
    ).all()
    return {
        "id": event.id,
        "creator_id": event.creator_id,
        "opportunity_id": event.opportunity_id,
        "name": event.name,
        "organizer": event.organizer,
        "description": event.description,
        "starts_at": start.isoformat() if start else None,
        "ends_at": end.isoformat() if end else None,
        "registration_deadline": deadline.isoformat() if deadline else None,
        "location": event.location,
        "event_url": event.event_url,
        "registration_url": event.registration_url,
        "eligibility": event.eligibility,
        "tags": split_list(event.tags),
        "event_format": event.event_format,
        "country": event.country,
        "region": event.region,
        "scope": event.scope,
        "registration_opens_at": _as_utc(event.registration_opens_at).isoformat() if event.registration_opens_at else None,
        "team_size_min": event.team_size_min,
        "team_size_max": event.team_size_max,
        "prize_details": event.prize_details,
        "event_status": event.event_status or "scheduled",
        "is_imported": event.is_imported is True,
        "source_name": event.source_name or "",
        "source_listings": [
            {
                "source_name": listing.source_name,
                "listing_url": listing.listing_url,
                "last_fetched_at": _as_utc(listing.last_fetched_at).isoformat(),
            }
            for listing in source_listings
        ],
        "source_confidence": event.source_confidence,
        "source_completeness": event.source_completeness,
        "source_updated_at": _as_utc(event.source_updated_at).isoformat() if event.source_updated_at else None,
        "last_fetched_at": _as_utc(event.last_fetched_at).isoformat() if event.last_fetched_at else None,
        "is_joined": joined,
        "is_completed": bool((end and end < current) or event.event_status == "expired"),
        "registration_deadline_pending": bool(deadline and current < deadline <= current + timedelta(days=7)),
        "can_edit": viewer_id == event.creator_id and event.is_imported is not True,
    }


@router.get("/calendar/events")
def list_events(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    search: str = Query(default="", max_length=120),
    scope: str | None = Query(default=None, max_length=30),
    country: str | None = Query(default=None, max_length=100),
    region: str | None = Query(default=None, max_length=100),
    event_format: str | None = Query(default=None, pattern="^(online|offline|hybrid)$"),
    technology: str | None = Query(default=None, max_length=80),
    eligibility: str | None = Query(default=None, max_length=200),
    deadline_before: datetime | None = None,
    source: str | None = Query(default=None, max_length=80),
    include_cancelled: bool = False,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    if from_date and to_date and to_date < from_date:
        raise HTTPException(status_code=422, detail="to_date must be on or after from_date")
    statement = select(HackathonEvent)
    if from_date:
        statement = statement.where(
            HackathonEvent.starts_at >= datetime.combine(from_date, time.min, timezone.utc).replace(tzinfo=None)
        )
    if to_date:
        statement = statement.where(
            HackathonEvent.starts_at <= datetime.combine(to_date, time.max, timezone.utc).replace(tzinfo=None)
        )
    if search.strip():
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            (HackathonEvent.name.ilike(pattern))
            | (HackathonEvent.organizer.ilike(pattern))
            | (HackathonEvent.description.ilike(pattern))
        )
    if scope:
        statement = statement.where(HackathonEvent.scope == scope.casefold().replace("-", "_"))
    if country:
        statement = statement.where(HackathonEvent.country.ilike(f"%{country.strip()}%"))
    if region:
        statement = statement.where(HackathonEvent.region.ilike(f"%{region.strip()}%"))
    if event_format:
        statement = statement.where(HackathonEvent.event_format == event_format)
    if technology:
        statement = statement.where(HackathonEvent.tags.ilike(f"%{technology.strip()}%"))
    if eligibility:
        statement = statement.where(HackathonEvent.eligibility.ilike(f"%{eligibility.strip()}%"))
    if deadline_before:
        if deadline_before.tzinfo is None:
            raise HTTPException(status_code=422, detail="deadline_before must include a timezone")
        statement = statement.where(HackathonEvent.registration_deadline <= deadline_before.astimezone(timezone.utc))
    if source:
        statement = statement.where(HackathonEvent.source_name.ilike(f"%{source.strip()}%"))
    if not include_cancelled:
        statement = statement.where(HackathonEvent.event_status != "cancelled")
    events = db.scalars(
        statement.order_by(HackathonEvent.starts_at.asc()).offset(offset).limit(limit)
    ).all()
    return [_event_data(event, user.id if user else None, db) for event in events]


@router.get("/calendar/recommendations")
def recommend_events(
    limit: int = Query(default=10, ge=1, le=50),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    user_terms = {
        item.casefold()
        for item in db.scalars(select(UserSkill.name).where(UserSkill.user_id == user.id))
    }
    user_terms.update(
        skill.name.casefold()
        for skill in db.scalars(select(DeveloperSkill).where(DeveloperSkill.user_id == user.id))
    )
    interests = {
        item.casefold()
        for item in db.scalars(select(UserInterest.name).where(UserInterest.user_id == user.id))
    }
    candidates = db.scalars(
        select(HackathonEvent)
        .where(
            HackathonEvent.starts_at > now_utc().replace(tzinfo=None),
            HackathonEvent.event_status == "scheduled",
            (HackathonEvent.registration_deadline.is_(None))
            | (HackathonEvent.registration_deadline > now_utc().replace(tzinfo=None)),
        )
        .order_by(HackathonEvent.starts_at.asc())
        .limit(500)
    ).all()
    ranked = []
    for event in candidates:
        tags = {tag.casefold() for tag in split_list(event.tags)}
        matching_skills = sorted(tags & user_terms)
        matching_interests = sorted(tags & interests)
        reasons = []
        if matching_skills:
            reasons.append(f"Your skills match event technologies: {', '.join(matching_skills)}")
        if matching_interests:
            reasons.append(f"Your interests match event topics: {', '.join(matching_interests)}")
        score = min(100, len(matching_skills) * 25 + len(matching_interests) * 15)
        if score:
            ranked.append({
                "event": _event_data(event, user.id, db),
                "estimated_match_score": score,
                "reasons": reasons,
            })
    ranked.sort(key=lambda item: (-item["estimated_match_score"], item["event"]["starts_at"]))
    return ranked[:limit]


@router.post("/calendar/events", status_code=201)
def create_event(
    data: HackathonEventIn, user: User = Depends(current_user), db: Session = Depends(get_db),
):
    if data.opportunity_id is not None and db.get(Opportunity, data.opportunity_id) is None:
        raise HTTPException(status_code=404, detail="Associated opportunity not found")
    event = HackathonEvent(
        creator_id=user.id,
        opportunity_id=data.opportunity_id,
        name=data.name.strip(),
        organizer=data.organizer.strip(),
        description=data.description.strip(),
        starts_at=data.starts_at.astimezone(timezone.utc),
        ends_at=data.ends_at.astimezone(timezone.utc),
        registration_deadline=data.registration_deadline.astimezone(timezone.utc) if data.registration_deadline else None,
        location=data.location.strip(),
        event_url=data.event_url,
        eligibility=data.eligibility.strip(),
        tags=csv_list(data.tags),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _event_data(event, user.id, db)


@router.get("/calendar/events/{event_id}")
def get_event(
    event_id: int, user: User | None = Depends(optional_user), db: Session = Depends(get_db),
):
    event = db.get(HackathonEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Hackathon event not found")
    return _event_data(event, user.id if user else None, db)


@router.put("/calendar/events/{event_id}")
def update_event(
    event_id: int, data: HackathonEventIn,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    event = db.get(HackathonEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Hackathon event not found")
    if event.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Only the event creator can edit this event")
    if event.is_imported:
        raise HTTPException(status_code=403, detail="Imported events are maintained by their source feed")
    if data.opportunity_id is not None and db.get(Opportunity, data.opportunity_id) is None:
        raise HTTPException(status_code=404, detail="Associated opportunity not found")
    for field in (
        "name", "organizer", "description", "location", "event_url", "eligibility",
    ):
        setattr(event, field, getattr(data, field).strip() if isinstance(getattr(data, field), str) else getattr(data, field))
    event.opportunity_id = data.opportunity_id
    event.starts_at = data.starts_at.astimezone(timezone.utc)
    event.ends_at = data.ends_at.astimezone(timezone.utc)
    event.registration_deadline = data.registration_deadline.astimezone(timezone.utc) if data.registration_deadline else None
    event.tags = csv_list(data.tags)
    db.commit()
    db.refresh(event)
    return _event_data(event, user.id, db)


@router.delete("/calendar/events/{event_id}", status_code=204)
def delete_event(
    event_id: int, user: User = Depends(current_user), db: Session = Depends(get_db),
):
    event = db.get(HackathonEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Hackathon event not found")
    if event.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Only the event creator can delete this event")
    if event.is_imported:
        raise HTTPException(status_code=403, detail="Imported events are maintained by their source feed")
    db.delete(event)
    db.commit()


@router.post("/calendar/events/{event_id}/register", status_code=201)
def register_for_event(
    event_id: int, user: User = Depends(current_user), db: Session = Depends(get_db),
):
    event = db.get(HackathonEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Hackathon event not found")
    if event.event_status == "cancelled":
        raise HTTPException(status_code=409, detail="Registration is not available for a cancelled event")
    now = now_utc()
    starts_at = _as_utc(event.starts_at)
    deadline = _as_utc(event.registration_deadline)
    if starts_at and starts_at <= now:
        raise HTTPException(status_code=409, detail="Registration is only available before the event starts")
    if deadline and deadline <= now:
        raise HTTPException(status_code=409, detail="The registration deadline has passed")
    registration = HackathonRegistration(event_id=event.id, user_id=user.id)
    db.add(registration)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="You are already registered for this event") from None
    return {"event_id": event.id, "is_joined": True}


@router.delete("/calendar/events/{event_id}/register", status_code=204)
def unregister_from_event(
    event_id: int, user: User = Depends(current_user), db: Session = Depends(get_db),
):
    registration = db.scalar(
        select(HackathonRegistration).where(
            HackathonRegistration.event_id == event_id,
            HackathonRegistration.user_id == user.id,
        )
    )
    if registration is None:
        raise HTTPException(status_code=404, detail="Event registration not found")
    db.delete(registration)
    db.commit()
