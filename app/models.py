from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def now_utc():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    college: Mapped[str] = mapped_column(String(160), default="")
    department: Mapped[str] = mapped_column(String(120), default="")
    photo_url: Mapped[str] = mapped_column(String(500), default="")
    experience: Mapped[str] = mapped_column(String(40), default="Beginner")
    preferred_role: Mapped[str] = mapped_column(String(80), default="")
    availability: Mapped[str] = mapped_column(String(160), default="")
    bio: Mapped[str] = mapped_column(Text, default="")
    project_experience: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class UserSkill(Base):
    __tablename__ = "user_skills"
    __table_args__ = (UniqueConstraint("user_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))


class UserInterest(Base):
    __tablename__ = "user_interests"
    __table_args__ = (UniqueConstraint("user_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(40), default="Hackathon")
    description: Mapped[str] = mapped_column(Text)
    required_skills: Mapped[str] = mapped_column(Text, default="")
    team_size: Mapped[int] = mapped_column(Integer, default=4)
    deadline: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    leader_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    required_skills: Mapped[str] = mapped_column(Text, default="")
    required_roles: Mapped[str] = mapped_column(Text, default="")
    max_size: Mapped[int] = mapped_column(Integer, default=4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(80), default="Member")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class TeamApplication(Base):
    __tablename__ = "team_applications"
    __table_args__ = (UniqueConstraint("team_id", "applicant_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    applicant_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="Todo")
    priority: Mapped[str] = mapped_column(String(20), default="Medium")
    due_date: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("team_id", "reviewer_id", "reviewee_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reviewee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    communication_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reliability_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    teamwork_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(String(300))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Roadmap(Base):
    __tablename__ = "roadmaps"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    domain: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str] = mapped_column(Text)
    steps: Mapped[str] = mapped_column(Text, default="")


class Challenge(Base):
    __tablename__ = "challenges"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    domain: Mapped[str] = mapped_column(String(80))
    difficulty: Mapped[str] = mapped_column(String(30))
    prompt: Mapped[str] = mapped_column(Text)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)


class DeveloperProfile(Base):
    __tablename__ = "developer_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    preferred_name: Mapped[str] = mapped_column(String(100), default="")
    headline: Mapped[str] = mapped_column(String(180), default="")
    degree: Mapped[str] = mapped_column(String(120), default="")
    course: Mapped[str] = mapped_column(String(120), default="")
    study_year: Mapped[str] = mapped_column(String(40), default="")
    graduation_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str] = mapped_column(String(120), default="")
    location_visible: Mapped[bool] = mapped_column(Boolean, default=False)
    education_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    collaboration_mode: Mapped[str] = mapped_column(String(40), default="")
    languages: Mapped[str] = mapped_column(String(500), default="")
    github_username: Mapped[str] = mapped_column(String(39), default="")
    resume_storage_key: Mapped[str] = mapped_column(String(80), default="")
    resume_visible: Mapped[bool] = mapped_column(Boolean, default=False)
    projects_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    history_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    credentials_visible: Mapped[bool] = mapped_column(Boolean, default=True)


class DeveloperSkill(Base):
    __tablename__ = "developer_skills"
    __table_args__ = (UniqueConstraint("user_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(40), default="Technology")
    proficiency: Mapped[int] = mapped_column(Integer, default=3)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class PortfolioProject(Base):
    __tablename__ = "portfolio_projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    technologies: Mapped[str] = mapped_column(String(500), default="")
    repository_url: Mapped[str] = mapped_column(String(500), default="")
    demo_url: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ProfileCredential(Base):
    __tablename__ = "profile_credentials"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    issuer: Mapped[str] = mapped_column(String(160), default="")
    evidence_url: Mapped[str] = mapped_column(String(500), default="")
    kind: Mapped[str] = mapped_column(String(30), default="Certification")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class HackathonHistory(Base):
    __tablename__ = "hackathon_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event_name: Mapped[str] = mapped_column(String(160))
    organizer: Mapped[str] = mapped_column(String(160), default="")
    event_date: Mapped[str] = mapped_column(String(40), default="")
    project_title: Mapped[str] = mapped_column(String(160), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    team_role: Mapped[str] = mapped_column(String(100), default="")
    technologies: Mapped[str] = mapped_column(String(500), default="")
    result: Mapped[str] = mapped_column(String(160), default="")
    repository_url: Mapped[str] = mapped_column(String(500), default="")
    demo_url: Mapped[str] = mapped_column(String(500), default="")
    evidence_url: Mapped[str] = mapped_column(String(500), default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class TeamInvitation(Base):
    __tablename__ = "team_invitations"
    __table_args__ = (
        Index(
            "uq_pending_team_invitation",
            "team_id", "invitee_id", unique=True,
            sqlite_where=text("status = 'pending'"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    inviter_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    invitee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class HackathonEvent(Base):
    __tablename__ = "hackathon_events"
    __table_args__ = (
        Index("ix_hackathon_events_source_status_start", "source_name", "event_status", "starts_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    organizer: Mapped[str] = mapped_column(String(160), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registration_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str] = mapped_column(String(200), default="")
    event_url: Mapped[str] = mapped_column(String(500), default="")
    registration_url: Mapped[str] = mapped_column(String(500), default="")
    eligibility: Mapped[str] = mapped_column(String(500), default="")
    tags: Mapped[str] = mapped_column(String(500), default="")
    event_format: Mapped[str] = mapped_column(String(20), default="")
    country: Mapped[str] = mapped_column(String(100), default="")
    region: Mapped[str] = mapped_column(String(100), default="")
    scope: Mapped[str] = mapped_column(String(30), default="")
    registration_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    team_size_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    team_size_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prize_details: Mapped[str] = mapped_column(Text, default="")
    event_status: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)
    is_imported: Mapped[bool] = mapped_column(Boolean, default=False)
    source_name: Mapped[str] = mapped_column(String(80), default="")
    source_confidence: Mapped[float | None] = mapped_column(nullable=True)
    source_completeness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class HackathonRegistration(Base):
    __tablename__ = "hackathon_registrations"
    __table_args__ = (UniqueConstraint("event_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("hackathon_events.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class EventSourceListing(Base):
    __tablename__ = "event_source_listings"
    __table_args__ = (UniqueConstraint("source_key", "source_event_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("hackathon_events.id", ondelete="CASCADE"), index=True)
    source_key: Mapped[str] = mapped_column(String(80))
    source_name: Mapped[str] = mapped_column(String(120))
    source_event_id: Mapped[str] = mapped_column(String(255))
    listing_url: Mapped[str] = mapped_column(String(1000), default="")
    last_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class EventSyncSource(Base):
    __tablename__ = "event_sync_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    source_name: Mapped[str] = mapped_column(String(120))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_found: Mapped[int] = mapped_column(Integer, default=0)
    last_created: Mapped[int] = mapped_column(Integer, default=0)
    last_updated: Mapped[int] = mapped_column(Integer, default=0)


class EventSyncRun(Base):
    __tablename__ = "event_sync_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    events_found: Mapped[int] = mapped_column(Integer, default=0)
    events_created: Mapped[int] = mapped_column(Integer, default=0)
    events_updated: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")


class EventSyncLock(Base):
    __tablename__ = "event_sync_locks"
    id: Mapped[int] = mapped_column(primary_key=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
