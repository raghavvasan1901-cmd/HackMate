from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Challenge, Roadmap


router = APIRouter(tags=["Learning and mock hackathons"])


@router.get("/roadmaps")
def list_roadmaps(domain: str = "", db: Session = Depends(get_db)):
    query = select(Roadmap)
    if domain:
        query = query.where(Roadmap.domain.ilike(f"%{domain.strip()}%"))
    return [
        {
            "id": item.id, "title": item.title, "domain": item.domain, "description": item.description,
            "steps": [step for step in item.steps.split("\n") if step],
        }
        for item in db.scalars(query.order_by(Roadmap.domain, Roadmap.title)).all()
    ]


@router.get("/challenges")
def list_challenges(domain: str = "", db: Session = Depends(get_db)):
    query = select(Challenge)
    if domain:
        query = query.where(Challenge.domain.ilike(f"%{domain.strip()}%"))
    return [
        {
            "id": item.id, "title": item.title, "domain": item.domain, "difficulty": item.difficulty,
            "prompt": item.prompt, "duration_minutes": item.duration_minutes,
        }
        for item in db.scalars(query.order_by(Challenge.id)).all()
    ]
