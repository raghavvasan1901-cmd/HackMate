from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    DeveloperProfile, DeveloperSkill, HackathonHistory, Opportunity, PortfolioProject, Review, Team,
    TeamApplication, TeamMember, User, UserInterest, UserSkill,
    Notification,
)
from app.schemas import ApplicationDecision, ApplicationIn, OpportunityIn, TeamIn
from app.security import current_user
from app.services.common import (
    csv_list, is_team_member, profile_data, require_team_member, split_list,
)


router = APIRouter(tags=["Opportunities and teams"])


def opportunity_data(item: Opportunity, db: Session):
    creator = db.get(User, item.creator_id)
    return {
        "id": item.id, "title": item.title, "kind": item.kind, "description": item.description,
        "required_skills": split_list(item.required_skills), "team_size": item.team_size,
        "deadline": item.deadline, "creator": creator.name if creator else "Unknown",
        "creator_id": item.creator_id, "created_at": item.created_at.isoformat(),
    }


def team_data(team: Team, db: Session):
    members = db.scalars(select(TeamMember).where(TeamMember.team_id == team.id)).all()
    profiles = []
    for member in members:
        user = db.get(User, member.user_id)
        if user:
            person = profile_data(user, db)
            profiles.append({"id": user.id, "name": user.name, "role": member.role, "skills": person["skills"]})
    opportunity = db.get(Opportunity, team.opportunity_id) if team.opportunity_id else None
    return {
        "id": team.id, "name": team.name, "description": team.description,
        "leader_id": team.leader_id, "opportunity_id": team.opportunity_id,
        "opportunity_title": opportunity.title if opportunity else None,
        "required_skills": split_list(team.required_skills), "required_roles": split_list(team.required_roles),
        "max_size": team.max_size, "members": profiles, "member_count": len(profiles),
        "created_at": team.created_at.isoformat(),
    }


@router.get("/opportunities")
def list_opportunities(
    search: str = "", kind: str = "", skill: str = "", db: Session = Depends(get_db)
):
    query = select(Opportunity)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(Opportunity.title.ilike(pattern), Opportunity.description.ilike(pattern)))
    if kind:
        query = query.where(Opportunity.kind == kind)
    if skill:
        query = query.where(Opportunity.required_skills.ilike(f"%{skill.strip()}%"))
    return [opportunity_data(row, db) for row in db.scalars(query.order_by(Opportunity.created_at.desc())).all()]


@router.post("/opportunities", status_code=201)
def create_opportunity(
    data: OpportunityIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    item = Opportunity(
        creator_id=user.id, title=data.title.strip(), kind=data.kind, description=data.description.strip(),
        required_skills=csv_list(data.required_skills), team_size=data.team_size, deadline=data.deadline,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return opportunity_data(item, db)


@router.get("/opportunities/{opportunity_id}")
def get_opportunity(opportunity_id: int, db: Session = Depends(get_db)):
    item = db.get(Opportunity, opportunity_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    result = opportunity_data(item, db)
    result["teams"] = [
        team_data(team, db) for team in db.scalars(select(Team).where(Team.opportunity_id == item.id)).all()
    ]
    return result


@router.get("/teams")
def list_teams(
    search: str = "", skill: str = "", db: Session = Depends(get_db)
):
    query = select(Team)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(Team.name.ilike(pattern), Team.description.ilike(pattern)))
    if skill:
        query = query.where(Team.required_skills.ilike(f"%{skill.strip()}%"))
    return [team_data(team, db) for team in db.scalars(query.order_by(Team.created_at.desc())).all()]


@router.post("/teams", status_code=201)
def create_team(data: TeamIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if data.opportunity_id and db.get(Opportunity, data.opportunity_id) is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    team = Team(
        leader_id=user.id, opportunity_id=data.opportunity_id, name=data.name.strip(),
        description=data.description.strip(), required_skills=csv_list(data.required_skills),
        required_roles=csv_list(data.required_roles), max_size=data.max_size,
    )
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id, role="Team Lead"))
    db.commit()
    db.refresh(team)
    return team_data(team, db)


@router.get("/teams/{team_id}")
def get_team(team_id: int, db: Session = Depends(get_db)):
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return team_data(team, db)


@router.post("/teams/{team_id}/applications", status_code=201)
def apply_to_team(
    team_id: int, data: ApplicationIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    if team.leader_id == user.id or is_team_member(team_id, user.id, db):
        raise HTTPException(status_code=409, detail="You are already a member of this team")
    existing = db.scalar(
        select(TeamApplication).where(TeamApplication.team_id == team_id, TeamApplication.applicant_id == user.id)
    )
    if existing:
        raise HTTPException(status_code=409, detail="You have already applied to this team")
    if team_data(team, db)["member_count"] >= team.max_size:
        raise HTTPException(status_code=409, detail="This team is full")
    application = TeamApplication(team_id=team.id, applicant_id=user.id, message=data.message.strip())
    db.add(application)
    db.add(Notification(user_id=team.leader_id, message=f"{user.name} applied to join {team.name}."))
    db.commit()
    return {"id": application.id, "status": application.status, "message": "Application submitted"}


@router.get("/teams/{team_id}/applications")
def list_applications(
    team_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    if team.leader_id != user.id:
        raise HTTPException(status_code=403, detail="Only the team leader can view applications")
    rows = db.scalars(select(TeamApplication).where(TeamApplication.team_id == team_id)).all()
    return [
        {
            "id": item.id, "team_id": item.team_id, "applicant": profile_data(db.get(User, item.applicant_id), db),
            "message": item.message, "status": item.status, "created_at": item.created_at.isoformat(),
        }
        for item in rows
    ]


@router.patch("/teams/{team_id}/applications/{application_id}")
def decide_application(
    team_id: int, application_id: int, data: ApplicationDecision,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    team = db.get(Team, team_id)
    application = db.get(TeamApplication, application_id)
    if team is None or application is None or application.team_id != team_id:
        raise HTTPException(status_code=404, detail="Application not found")
    if team.leader_id != user.id:
        raise HTTPException(status_code=403, detail="Only the team leader can decide applications")
    if application.status != "pending":
        raise HTTPException(status_code=409, detail="This application has already been decided")
    if data.status == "accepted":
        if team_data(team, db)["member_count"] >= team.max_size:
            raise HTTPException(status_code=409, detail="This team is full")
        db.add(TeamMember(team_id=team_id, user_id=application.applicant_id, role="Member"))
    application.status = data.status
    applicant = db.get(User, application.applicant_id)
    db.add(Notification(user_id=application.applicant_id, message=f"Your application to {team.name} was {data.status}."))
    db.commit()
    return {"id": application.id, "status": application.status}


def teammate_recommendations(team: Team, user: User, db: Session):
    existing = set(db.scalars(select(TeamMember.user_id).where(TeamMember.team_id == team.id)))
    if team.leader_id:
        existing.add(team.leader_id)
    current_skill_set = {
        skill.lower()
        for member_id in existing
        for skill in db.scalars(select(UserSkill.name).where(UserSkill.user_id == member_id))
    }
    current_skill_set.update(
        skill.name.lower()
        for member_id in existing
        for skill in db.scalars(select(DeveloperSkill).where(DeveloperSkill.user_id == member_id))
    )
    required_skills = {value.lower() for value in split_list(team.required_skills)}
    missing = required_skills - current_skill_set
    required_roles = {value.lower() for value in split_list(team.required_roles)}
    team_interests = {
        interest.lower()
        for member_id in existing
        for interest in db.scalars(select(UserInterest.name).where(UserInterest.user_id == member_id))
    }
    user_skills = {value.lower() for value in db.scalars(select(UserSkill.name).where(UserSkill.user_id == user.id))}
    detailed_skills = db.scalars(select(DeveloperSkill).where(DeveloperSkill.user_id == user.id)).all()
    user_skills.update(skill.name.lower() for skill in detailed_skills)
    user_interests = {value.lower() for value in db.scalars(select(UserInterest.name).where(UserInterest.user_id == user.id))}
    useful_skills = user_skills & (missing if required_skills else user_skills - current_skill_set)
    proficiency_by_name = {skill.name.lower(): skill.proficiency for skill in detailed_skills}
    skill_score = (
        sum(proficiency_by_name.get(name, 3) / 5 for name in useful_skills)
        / max(1, len(missing if required_skills else user_skills)) * 100
    )
    interest_score = len(user_interests & team_interests) / max(1, len(user_interests | team_interests)) * 100
    role_score = 100 if user.preferred_role.lower() in required_roles and user.preferred_role else 0
    team_experience = [
        db.get(User, member_id).experience for member_id in existing if db.get(User, member_id)
    ]
    # A mix of levels is useful; exact level matches receive partial credit.
    experience_score = 100 if not team_experience or user.experience not in team_experience else 65
    availability_score = 100 if user.availability else 0
    portfolio = db.scalar(
        select(DeveloperProfile).where(DeveloperProfile.user_id == user.id)
    )
    history = db.scalars(
        select(HackathonHistory).where(HackathonHistory.user_id == user.id)
    ).all() if portfolio is None or portfolio.history_visible else []
    projects = db.scalars(
        select(PortfolioProject).where(PortfolioProject.user_id == user.id)
    ).all() if portfolio is None or portfolio.projects_visible else []
    relevant_history = [
        item for item in history
        if set(value.lower() for value in split_list(item.technologies)) & (missing or user_skills)
        or (item.team_role and item.team_role.lower() in required_roles)
    ]
    relevant_projects = [
        item for item in projects
        if set(value.lower() for value in split_list(item.technologies)) & (missing or user_skills)
    ]
    relevant_experience_count = len(relevant_history) + len(relevant_projects)
    history_score = 50 if not history and not projects else min(100, 45 + 15 * relevant_experience_count)
    score = round(
        skill_score * 0.40 + interest_score * 0.17 + role_score * 0.14
        + experience_score * 0.08 + availability_score * 0.08 + history_score * 0.13
    )
    reviews = db.scalars(select(Review).where(Review.reviewee_id == user.id)).all()
    rating = (sum(review.rating for review in reviews) / len(reviews)) if reviews else None
    experience_items = [
        {
            "event_name": item.event_name, "project_title": item.project_title,
            "team_role": item.team_role, "technologies": split_list(item.technologies),
            "result": item.result, "verified": False,
        }
        for item in relevant_history[:3]
    ]
    project_items = [
        {
            "title": item.title, "technologies": split_list(item.technologies),
            "verified": False,
        }
        for item in relevant_projects[:3]
    ]
    explanation_parts = []
    if useful_skills:
        explanation_parts.append(f"Can contribute {', '.join(sorted(useful_skills))}")
    if user.preferred_role and user.preferred_role.lower() in required_roles:
        explanation_parts.append(f"matches the requested {user.preferred_role} role")
    if experience_items:
        explanation_parts.append(f"reports relevant experience from {len(experience_items)} hackathon(s)")
    if user.availability:
        explanation_parts.append("has stated availability")
    return {
        "user": profile_data(user, db), "score": min(100, score), "score_is_estimate": True,
        "score_breakdown": {
            "complementary_skills": round(skill_score), "shared_interests": round(interest_score),
            "required_role": role_score, "experience_mix": experience_score, "availability": availability_score,
            "relevant_hackathon_experience": history_score,
        },
        "complementary_skills": sorted(useful_skills),
        "strong_matching_skills": sorted(user_skills & current_skill_set),
        "missing_skills_candidate_contributes": sorted(useful_skills),
        "relevant_hackathon_experience": experience_items,
        "relevant_project_experience": project_items,
        "role_compatibility": bool(user.preferred_role and user.preferred_role.lower() in required_roles),
        "availability_compatibility": bool(user.availability),
        "reputation": {"average_rating": round(rating, 1) if rating is not None else None, "review_count": len(reviews)},
        "explanation": ". ".join(explanation_parts) + ("." if explanation_parts else "Could add a complementary perspective to the team."),
        "explanation_method": "rule_based",
    }


@router.get("/teams/{team_id}/matches")
def team_matches(
    team_id: int, limit: int = Query(default=12, ge=1, le=50),
    user: User = Depends(current_user), db: Session = Depends(get_db),
    explain_with_ai: bool = False,
):
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    if not is_team_member(team_id, user.id, db):
        raise HTTPException(status_code=403, detail="Team membership required")
    members = set(db.scalars(select(TeamMember.user_id).where(TeamMember.team_id == team_id)))
    candidates = db.scalars(select(User).where(User.id.not_in(members))).all()
    results = [teammate_recommendations(team, candidate, db) for candidate in candidates]
    ranked = sorted(results, key=lambda result: result["score"], reverse=True)[:limit]
    _add_optional_ai_explanations(user, db, ranked, explain_with_ai)
    return ranked


@router.get("/opportunities/{opportunity_id}/matches")
def opportunity_matches(
    opportunity_id: int, limit: int = Query(default=12, ge=1, le=50),
    explain_with_ai: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db),
):
    opportunity = db.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    associated_members = set()
    if opportunity.creator_id:
        associated_members.add(opportunity.creator_id)
    associated_team_ids = db.scalars(
        select(Team.id).where(Team.opportunity_id == opportunity_id)
    ).all()
    if associated_team_ids:
        associated_members.update(db.scalars(
            select(TeamMember.user_id).where(TeamMember.team_id.in_(associated_team_ids))
        ))
    context = Team(
        id=-opportunity.id,
        leader_id=opportunity.creator_id,
        opportunity_id=opportunity.id,
        name=opportunity.title,
        description=opportunity.description,
        required_skills=opportunity.required_skills,
        required_roles="",
        max_size=opportunity.team_size,
    )
    candidates = db.scalars(select(User).where(User.id.not_in(associated_members))).all()
    ranked = sorted(
        (teammate_recommendations(context, candidate, db) for candidate in candidates),
        key=lambda result: result["score"], reverse=True,
    )[:limit]
    _add_optional_ai_explanations(user, db, ranked, explain_with_ai)
    return ranked


def _add_optional_ai_explanations(user: User, db: Session, results: list[dict], enabled: bool) -> None:
    for item in results:
        item["ai_explanation"] = None
    if not enabled:
        return
    from app.services.ai_service import AIService

    outcome = AIService.explain_matches(user, results[:5])
    for item, explanation in zip(results, outcome.get("explanations", [])):
        if explanation:
            item["ai_explanation"] = explanation
            item["explanation_method"] = "ai"
    for item in results:
        item["ai_explanation_status"] = outcome.get("status", "unavailable")


@router.get("/teams/{team_id}/balance")
def team_balance(team_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    if not is_team_member(team_id, user.id, db):
        raise HTTPException(status_code=403, detail="Team membership required")
    member_ids = set(db.scalars(select(TeamMember.user_id).where(TeamMember.team_id == team_id)))
    all_skills = [
        skill for member_id in member_ids
        for skill in db.scalars(select(UserSkill.name).where(UserSkill.user_id == member_id))
    ]
    counts: dict[str, int] = {}
    for skill in all_skills:
        counts[skill] = counts.get(skill, 0) + 1
    required = {value.lower(): value for value in split_list(team.required_skills)}
    if team.opportunity_id:
        opportunity = db.get(Opportunity, team.opportunity_id)
        if opportunity:
            required.update({value.lower(): value for value in split_list(opportunity.required_skills)})
    present_lower = {value.lower() for value in counts}
    missing = [value for key, value in required.items() if key not in present_lower]
    return {
        "team_id": team_id, "skill_counts": counts, "required_skills": list(required.values()),
        "missing_skills": missing,
        "underrepresented_skills": [skill for skill, count in counts.items() if count == 1],
        "suggested_roles": split_list(team.required_roles),
        "recommendations": team_matches(team_id, 5, user, db),
    }
