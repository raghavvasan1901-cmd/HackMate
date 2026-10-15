from datetime import date, datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


def _validate_external_url(value: str) -> str:
    value = value.strip()
    if value and (urlsplit(value).scheme not in {"http", "https"} or not urlsplit(value).netloc):
        raise ValueError("URL must be an absolute http or https address")
    return value


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ProfileIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    college: str = Field(default="", max_length=160)
    department: str = Field(default="", max_length=120)
    photo_url: str = Field(default="", max_length=500)
    experience: str = Field(default="Beginner", max_length=40)
    preferred_role: str = Field(default="", max_length=80)
    availability: str = Field(default="", max_length=160)
    bio: str = Field(default="", max_length=1200)
    project_experience: str = Field(default="", max_length=2000)
    skills: list[str] = Field(default_factory=list, max_length=40)
    interests: list[str] = Field(default_factory=list, max_length=40)


class OpportunityIn(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    kind: str = Field(default="Hackathon", max_length=40)
    description: str = Field(min_length=10, max_length=5000)
    required_skills: list[str] = Field(default_factory=list, max_length=30)
    team_size: int = Field(default=4, ge=1, le=20)
    deadline: str = Field(default="", max_length=40)


class TeamIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=3000)
    required_skills: list[str] = Field(default_factory=list, max_length=30)
    required_roles: list[str] = Field(default_factory=list, max_length=20)
    max_size: int = Field(default=4, ge=2, le=20)
    opportunity_id: int | None = None


class ApplicationIn(BaseModel):
    message: str = Field(default="", max_length=1000)


class ApplicationDecision(BaseModel):
    status: str = Field(pattern="^(accepted|rejected)$")


class TaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    description: str = Field(default="", max_length=3000)
    assignee_id: int | None = None
    status: str = Field(default="Todo", pattern="^(Todo|In Progress|Done)$")
    priority: str = Field(default="Medium", pattern="^(Low|Medium|High)$")
    due_date: str = Field(default="", max_length=40)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=3000)
    assignee_id: int | None = None
    status: str | None = Field(default=None, pattern="^(Todo|In Progress|Done)$")
    priority: str | None = Field(default=None, pattern="^(Low|Medium|High)$")
    due_date: str | None = Field(default=None, max_length=40)


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class ReviewIn(BaseModel):
    reviewee_id: int
    rating: int = Field(ge=1, le=5)
    communication_rating: int | None = Field(default=None, ge=1, le=5)
    reliability_rating: int | None = Field(default=None, ge=1, le=5)
    teamwork_rating: int | None = Field(default=None, ge=1, le=5)
    feedback: str = Field(default="", max_length=2000)


class AIChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=100, pattern="^[a-zA-Z0-9_-]+$")


class DeveloperProfileIn(BaseModel):
    preferred_name: str | None = Field(default=None, max_length=100)
    headline: str | None = Field(default=None, max_length=180)
    degree: str | None = Field(default=None, max_length=120)
    course: str | None = Field(default=None, max_length=120)
    study_year: str | None = Field(default=None, max_length=40)
    graduation_year: int | None = Field(default=None, ge=1950, le=2150)
    location: str | None = Field(default=None, max_length=120)
    location_visible: bool | None = None
    education_visible: bool | None = None
    collaboration_mode: str | None = Field(default=None, max_length=40)
    languages: list[str] | None = Field(default=None, max_length=20)
    github_username: str | None = Field(default=None, max_length=39, pattern="^[A-Za-z0-9-]*$")
    resume_visible: bool | None = None
    projects_visible: bool | None = None
    history_visible: bool | None = None
    credentials_visible: bool | None = None


class DeveloperSkillIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    category: str = Field(default="Technology", max_length=40)
    proficiency: int = Field(default=3, ge=1, le=5)


class PortfolioProjectIn(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=3000)
    technologies: list[str] = Field(default_factory=list, max_length=30)
    repository_url: str = Field(default="", max_length=500)
    demo_url: str = Field(default="", max_length=500)

    @field_validator("repository_url", "demo_url")
    @classmethod
    def validate_urls(cls, value: str) -> str:
        return _validate_external_url(value)


class ProfileCredentialIn(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    issuer: str = Field(default="", max_length=160)
    evidence_url: str = Field(default="", max_length=500)
    kind: str = Field(default="Certification", pattern="^(Certification|Course|Achievement)$")

    @field_validator("evidence_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _validate_external_url(value)


class HackathonHistoryIn(BaseModel):
    event_name: str = Field(min_length=2, max_length=160)
    organizer: str = Field(default="", max_length=160)
    event_date: str = Field(default="", max_length=40)
    project_title: str = Field(default="", max_length=160)
    summary: str = Field(default="", max_length=3000)
    team_role: str = Field(default="", max_length=100)
    technologies: list[str] = Field(default_factory=list, max_length=30)
    result: str = Field(default="", max_length=160)
    repository_url: str = Field(default="", max_length=500)
    demo_url: str = Field(default="", max_length=500)
    evidence_url: str = Field(default="", max_length=500)

    @field_validator("repository_url", "demo_url", "evidence_url")
    @classmethod
    def validate_urls(cls, value: str) -> str:
        return _validate_external_url(value)

    @field_validator("event_date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        value = value.strip()
        if value:
            date.fromisoformat(value)
        return value


class TeamInvitationIn(BaseModel):
    invitee_id: int = Field(gt=0)
    message: str = Field(default="", max_length=1000)


class TeamInvitationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern="^(accepted|declined)$")


class HackathonEventIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    organizer: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=5000)
    starts_at: datetime
    ends_at: datetime
    registration_deadline: datetime | None = None
    location: str = Field(default="", max_length=200)
    event_url: str = Field(default="", max_length=500)
    eligibility: str = Field(default="", max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=30)
    opportunity_id: int | None = Field(default=None, gt=0)

    @field_validator("event_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _validate_external_url(value)

    @model_validator(mode="after")
    def validate_event_times(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("Event timestamps must include a timezone")
        if self.registration_deadline and self.registration_deadline.tzinfo is None:
            raise ValueError("Registration deadline must include a timezone")
        if self.ends_at <= self.starts_at:
            raise ValueError("Event end must be after its start")
        if self.registration_deadline and self.registration_deadline >= self.starts_at:
            raise ValueError("Registration deadline must be before the event starts")
        return self


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
