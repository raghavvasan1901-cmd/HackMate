from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    DeveloperProfile, DeveloperSkill, HackathonHistory, Notification, Team, TeamApplication, TeamInvitation, TeamMember,
    User, UserSkill,
)
from app.schemas import TeamInvitationDecision, TeamInvitationIn
from app.security import current_user
from app.services.common import is_team_member, profile_data
from app.models import now_utc


router = APIRouter(tags=["Team invitations"])
INVITATION_DAYS_VALID = 14


def _expire_old(db: Session, user_id: int | None = None) -> None:
    statement = update(TeamInvitation).where(
        TeamInvitation.status == "pending",
        TeamInvitation.expires_at <= now_utc(),
    )
    if user_id is not None:
        statement = statement.where(
            (TeamInvitation.invitee_id == user_id) | (TeamInvitation.inviter_id == user_id)
        )
    db.execute(statement.values(status="expired").execution_options(synchronize_session=False))


def _invitation_data(invitation: TeamInvitation, db: Session) -> dict:
    team = db.get(Team, invitation.team_id)
    inviter = db.get(User, invitation.inviter_id)
    invitee = db.get(User, invitation.invitee_id)
    return {
        "id": invitation.id,
        "team_id": invitation.team_id,
        "team_name": team.name if team else "Team removed",
        "inviter": profile_data(inviter, db) if inviter else None,
        "invitee": profile_data(invitee, db) if invitee else None,
        "message": invitation.message,
        "status": invitation.status,
        "created_at": invitation.created_at.isoformat(),
        "expires_at": invitation.expires_at.isoformat(),
    }


@router.get("/users/search")
def search_users(
    q: str = Query(min_length=2, max_length=80),
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    pattern = f"%{q.strip()}%"
    matched_ids = select(UserSkill.user_id).where(UserSkill.name.ilike(pattern))
    detailed_skill_ids = select(DeveloperSkill.user_id).where(DeveloperSkill.name.ilike(pattern))
    users = db.scalars(
        select(User).where(
            User.id != user.id,
            or_(
                User.name.ilike(pattern), User.preferred_role.ilike(pattern),
                User.id.in_(matched_ids), User.id.in_(detailed_skill_ids),
            ),
        ).order_by(User.name.asc()).limit(20)
    ).all()
    results = []
    for candidate in users:
        portfolio = db.scalar(
            select(DeveloperProfile).where(DeveloperProfile.user_id == candidate.id)
        )
        skills = list(db.scalars(select(UserSkill.name).where(UserSkill.user_id == candidate.id)))
        skills.extend(
            name for name in db.scalars(
                select(DeveloperSkill.name).where(DeveloperSkill.user_id == candidate.id)
            ) if name not in skills
        )
        experience_count = db.scalar(
            select(func.count(HackathonHistory.id)).where(HackathonHistory.user_id == candidate.id)
        ) or 0
        results.append({
            "id": candidate.id, "name": candidate.name, "preferred_role": candidate.preferred_role,
            "experience": candidate.experience, "skills": skills, "availability": candidate.availability,
            "hackathon_experience_count": experience_count,
            "photo_url": candidate.photo_url,
            "can_show_github": bool(portfolio and portfolio.github_username and portfolio.credentials_visible),
        })
    return results


@router.post("/teams/{team_id}/invitations", status_code=201)
def send_invitation(
    team_id: int, data: TeamInvitationIn, user: User = Depends(current_user), db: Session = Depends(get_db),
):
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    if team.leader_id != user.id:
        raise HTTPException(status_code=403, detail="Only the team leader can invite teammates")
    invitee = db.get(User, data.invitee_id)
    if invitee is None:
        raise HTTPException(status_code=404, detail="HackMate user not found")
    if invitee.id == user.id:
        raise HTTPException(status_code=422, detail="You cannot invite yourself")
    if is_team_member(team_id, invitee.id, db):
        raise HTTPException(status_code=409, detail="This user is already a team member")
    member_count = db.scalar(select(func.count(TeamMember.id)).where(TeamMember.team_id == team_id)) or 0
    if member_count >= team.max_size:
        raise HTTPException(status_code=409, detail="This team is full")
    _expire_old(db, invitee.id)
    existing = db.scalar(
        select(TeamInvitation).where(
            TeamInvitation.team_id == team_id,
            TeamInvitation.invitee_id == invitee.id,
            TeamInvitation.status == "pending",
        )
    )
    if existing:
        db.rollback()
        raise HTTPException(status_code=409, detail="A pending invitation already exists")
    now = now_utc()
    invitation = TeamInvitation(
        team_id=team_id, inviter_id=user.id, invitee_id=invitee.id,
        message=data.message.strip(), status="pending",
        created_at=now, expires_at=now + timedelta(days=INVITATION_DAYS_VALID),
    )
    db.add(invitation)
    db.add(Notification(user_id=invitee.id, message=f"{user.name} invited you to join {team.name}."))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A pending invitation already exists") from None
    db.refresh(invitation)
    return _invitation_data(invitation, db)


@router.get("/invitations")
def list_invitations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    _expire_old(db, user.id)
    db.commit()
    received = db.scalars(
        select(TeamInvitation).where(TeamInvitation.invitee_id == user.id)
        .order_by(TeamInvitation.created_at.desc())
    ).all()
    sent = db.scalars(
        select(TeamInvitation).where(TeamInvitation.inviter_id == user.id)
        .order_by(TeamInvitation.created_at.desc())
    ).all()
    return {
        "received": [_invitation_data(item, db) for item in received],
        "sent": [_invitation_data(item, db) for item in sent],
    }


@router.patch("/invitations/{invitation_id}")
def respond_to_invitation(
    invitation_id: int, data: TeamInvitationDecision,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    status = data.status
    invitation = db.get(TeamInvitation, invitation_id)
    if invitation is None or invitation.invitee_id != user.id:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.status != "pending":
        raise HTTPException(status_code=409, detail=f"This invitation is {invitation.status}")
    if invitation.expires_at.replace(tzinfo=now_utc().tzinfo) <= now_utc():
        invitation.status = "expired"
        db.commit()
        raise HTTPException(status_code=409, detail="This invitation has expired")
    if status == "declined":
        changed = db.execute(
            update(TeamInvitation).where(
                TeamInvitation.id == invitation_id, TeamInvitation.invitee_id == user.id,
                TeamInvitation.status == "pending",
            ).values(status="declined")
        )
        if changed.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="This invitation is no longer pending")
        db.add(Notification(
            user_id=invitation.inviter_id,
            message=f"{user.name} declined the invitation to join "
            f"{getattr(db.get(Team, invitation.team_id), 'name', 'a team')}.",
        ))
        db.commit()
        db.refresh(invitation)
        return _invitation_data(invitation, db)

    team = db.get(Team, invitation.team_id)
    if team is None:
        raise HTTPException(status_code=409, detail="The invited team no longer exists")
    changed = db.execute(
        update(TeamInvitation).where(
            TeamInvitation.id == invitation_id,
            TeamInvitation.invitee_id == user.id,
            TeamInvitation.status == "pending",
            TeamInvitation.expires_at > now_utc(),
        ).values(status="accepted").execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="This invitation expired or was already handled")
    invitation.status = "accepted"
    member_count = db.scalar(select(func.count(TeamMember.id)).where(TeamMember.team_id == team.id)) or 0
    if member_count >= team.max_size:
        db.rollback()
        raise HTTPException(status_code=409, detail="The team is now full; the invitation was not accepted")
    if is_team_member(team.id, user.id, db):
        db.rollback()
        raise HTTPException(status_code=409, detail="You are already a member of this team")
    db.add(TeamMember(team_id=team.id, user_id=user.id, role="Member"))
    pending_application = db.scalar(
        select(TeamApplication).where(
            TeamApplication.team_id == team.id, TeamApplication.applicant_id == user.id,
            TeamApplication.status == "pending",
        )
    )
    if pending_application:
        pending_application.status = "accepted"
    db.add(Notification(user_id=user.id, message=f"You joined {team.name} after accepting the invitation."))
    db.add(Notification(user_id=invitation.inviter_id, message=f"{user.name} accepted the invitation to {team.name}."))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Membership was already added") from None
    db.refresh(invitation)
    return _invitation_data(invitation, db)


@router.delete("/invitations/{invitation_id}", status_code=204)
def cancel_invitation(
    invitation_id: int, user: User = Depends(current_user), db: Session = Depends(get_db),
):
    invitation = db.get(TeamInvitation, invitation_id)
    if invitation is None or invitation.inviter_id != user.id:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending invitations can be cancelled")
    invitation.status = "cancelled"
    team = db.get(Team, invitation.team_id)
    db.add(Notification(
        user_id=invitation.invitee_id,
        message=f"Your invitation to {team.name if team else 'a team'} was cancelled.",
    ))
    db.commit()
