import os
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EventSyncRun, EventSyncSource, User
from app.security import current_user
from app.services.event_sync import configured_sources, sync_event_sources


router = APIRouter(tags=["Hackathon event synchronization"])


def _require_sync_admin(user: User) -> None:
    configured_ids = os.getenv("HACKMATE_SYNC_ADMIN_USER_IDS", "")
    try:
        admin_ids = {int(value.strip()) for value in configured_ids.split(",") if value.strip()}
    except ValueError:
        raise HTTPException(status_code=503, detail="Hackathon sync administrator configuration is invalid") from None
    if not admin_ids or user.id not in admin_ids:
        raise HTTPException(status_code=403, detail="Administrator permission is required")


def _iso(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


@router.get("/admin/event-sync/sources")
def get_sync_sources(user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require_sync_admin(user)
    try:
        sources = configured_sources()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    states = {
        row.source_key: row
        for row in db.scalars(select(EventSyncSource)).all()
    }
    return [
        {
            "key": source.key,
            "name": source.name,
            "type": "iCalendar",
            "configured": True,
            "last_attempt_at": _iso(states[source.key].last_attempt_at) if source.key in states else None,
            "last_success_at": _iso(states[source.key].last_success_at) if source.key in states else None,
            "last_error": states[source.key].last_error if source.key in states else "",
            "last_found": states[source.key].last_found if source.key in states else 0,
            "last_created": states[source.key].last_created if source.key in states else 0,
            "last_updated": states[source.key].last_updated if source.key in states else 0,
        }
        for source in sources
    ]


@router.post("/admin/event-sync/run")
def run_sync(user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require_sync_admin(user)
    try:
        result = sync_event_sources(db, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    if result["status"] == "already_running":
        raise HTTPException(status_code=409, detail="A synchronization is already in progress")
    return result


@router.get("/admin/event-sync/runs")
def list_sync_runs(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _require_sync_admin(user)
    runs = db.scalars(
        select(EventSyncRun).order_by(EventSyncRun.started_at.desc()).limit(limit)
    ).all()
    return [
        {
            "id": run.id,
            "started_at": _iso(run.started_at),
            "finished_at": _iso(run.finished_at),
            "status": run.status,
            "source_count": run.source_count,
            "events_found": run.events_found,
            "events_created": run.events_created,
            "events_updated": run.events_updated,
            "failure_count": run.failure_count,
            "summary": run.summary,
        }
        for run in runs
    ]
