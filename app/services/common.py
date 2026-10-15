from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Review, Team, TeamMember, User, UserInterest, UserSkill,
)


def split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def csv_list(values: list[str]) -> str:
    return ",".join(dict.fromkeys(value.strip() for value in values if value.strip()))


def profile_data(user: User, db: Session, include_email: bool = False) -> dict:
    skills = list(db.scalars(select(UserSkill.name).where(UserSkill.user_id == user.id)))
    interests = list(db.scalars(select(UserInterest.name).where(UserInterest.user_id == user.id)))
    rating = db.scalar(select(func.avg(Review.rating)).where(Review.reviewee_id == user.id))
    result = {
        "id": user.id, "name": user.name, "college": user.college,
        "department": user.department, "photo_url": user.photo_url, "experience": user.experience,
        "preferred_role": user.preferred_role, "availability": user.availability, "bio": user.bio,
        "project_experience": user.project_experience, "skills": skills, "interests": interests,
        "average_rating": round(rating, 1) if rating is not None else None,
    }
    if include_email:
        result["email"] = user.email
    return result


def require_team_member(team_id: int, user: User, db: Session) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    is_member = db.scalar(
        select(TeamMember.id).where(TeamMember.team_id == team_id, TeamMember.user_id == user.id)
    )
    if not is_member:
        raise HTTPException(status_code=403, detail="Team membership required")
    return team


def is_team_member(team_id: int, user_id: int, db: Session) -> bool:
    return db.scalar(
        select(TeamMember.id).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
    ) is not None
