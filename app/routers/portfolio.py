import os
import re
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    DeveloperProfile, DeveloperSkill, HackathonHistory, PortfolioProject, ProfileCredential, User,
)
from app.schemas import (
    DeveloperProfileIn, DeveloperSkillIn, HackathonHistoryIn, PortfolioProjectIn, ProfileCredentialIn,
)
from app.security import current_user, optional_user
from app.services.common import csv_list, profile_data, split_list


router = APIRouter(tags=["Developer portfolio"])
MAX_RESUME_BYTES = 5 * 1024 * 1024
STORAGE_KEY_PATTERN = re.compile(r"^[a-f0-9]{32}\.pdf$")


def _profile_record(user_id: int, db: Session) -> DeveloperProfile:
    record = db.scalar(select(DeveloperProfile).where(DeveloperProfile.user_id == user_id))
    if record is None:
        record = DeveloperProfile(user_id=user_id)
        db.add(record)
        db.flush()
    return record


def _can_view_private(record: DeveloperProfile, viewer: User | None, owner: User) -> bool:
    return viewer is not None and viewer.id == owner.id


def _portfolio_data(owner: User, viewer: User | None, db: Session) -> dict:
    record = db.scalar(select(DeveloperProfile).where(DeveloperProfile.user_id == owner.id))
    if record is None:
        record = DeveloperProfile(
            user_id=owner.id, preferred_name="", headline="", degree="", course="", study_year="",
            location="", location_visible=False, education_visible=True, collaboration_mode="",
            languages="", github_username="", resume_storage_key="", resume_visible=False,
            projects_visible=True, history_visible=True, credentials_visible=True,
        )
    is_owner = viewer is not None and viewer.id == owner.id
    location_visible = record.location_visible is True
    education_visible = record.education_visible is not False
    resume_visible = record.resume_visible is True
    projects_visible = record.projects_visible is not False
    history_visible = record.history_visible is not False
    credentials_visible = record.credentials_visible is not False
    base = profile_data(owner, db)
    base.update({
        "preferred_name": record.preferred_name,
        "display_name": record.preferred_name or owner.name,
        "headline": record.headline,
        "degree": record.degree,
        "course": record.course,
        "study_year": record.study_year,
        "graduation_year": record.graduation_year,
        "location": record.location,
        "collaboration_mode": record.collaboration_mode,
        "languages": split_list(record.languages or ""),
        "github_username": record.github_username,
        "resume_available": bool(record.resume_storage_key) and (is_owner or resume_visible),
        "resume_visible": resume_visible if is_owner else False,
        "privacy": {
            "projects_visible": projects_visible,
            "history_visible": history_visible,
            "credentials_visible": credentials_visible,
            "location_visible": location_visible,
            "education_visible": education_visible,
        },
        "skills_detail": [
            {
                "id": skill.id, "name": skill.name, "category": skill.category,
                "proficiency": skill.proficiency, "verified": skill.verified,
            }
            for skill in db.scalars(select(DeveloperSkill).where(DeveloperSkill.user_id == owner.id))
        ],
    })
    if is_owner:
        base["resume_visible"] = resume_visible
        base["privacy"]["resume_visible"] = resume_visible
        base["privacy"]["github_username_visible"] = True
    elif resume_visible and record.resume_storage_key:
        base["resume_download_url"] = f"/api/users/{owner.id}/resume"
    if not is_owner and not location_visible:
        base["location"] = ""
    if not is_owner and not education_visible:
        base.update({"college": "", "department": "", "degree": "", "course": "", "study_year": "", "graduation_year": None})
    elif not projects_visible:
        base["privacy"]["projects_visible"] = False
    if projects_visible or is_owner:
        base["projects"] = [
            {
                "id": item.id, "title": item.title, "description": item.description,
                "technologies": split_list(item.technologies), "repository_url": item.repository_url,
                "demo_url": item.demo_url,
            }
            for item in db.scalars(
                select(PortfolioProject).where(PortfolioProject.user_id == owner.id)
                .order_by(PortfolioProject.created_at.desc())
            )
        ]
    else:
        base["projects"] = []
    if credentials_visible or is_owner:
        base["credentials"] = [
            {
                "id": item.id, "title": item.title, "issuer": item.issuer, "kind": item.kind,
                "evidence_url": item.evidence_url,
            }
            for item in db.scalars(
                select(ProfileCredential).where(ProfileCredential.user_id == owner.id)
                .order_by(ProfileCredential.created_at.desc())
            )
        ]
    else:
        base["credentials"] = []
    if history_visible or is_owner:
        base["hackathon_history"] = [
            {
                "id": item.id, "event_name": item.event_name, "organizer": item.organizer,
                "event_date": item.event_date, "project_title": item.project_title,
                "summary": item.summary, "team_role": item.team_role,
                "technologies": split_list(item.technologies), "result": item.result,
                "repository_url": item.repository_url, "demo_url": item.demo_url,
                "evidence_url": item.evidence_url, "verified": item.verified,
            }
            for item in db.scalars(
                select(HackathonHistory).where(HackathonHistory.user_id == owner.id)
                .order_by(HackathonHistory.event_date.desc())
            )
        ]
    else:
        base["hackathon_history"] = []
    if not is_owner and not credentials_visible:
        base["github_username"] = ""
    if is_owner:
        base["resume_download_url"] = f"/api/users/{owner.id}/resume" if record.resume_storage_key else None
    return base


@router.get("/users/me/portfolio")
def my_portfolio(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _portfolio_data(user, user, db)


@router.put("/users/me/portfolio")
def update_portfolio(
    data: DeveloperProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db),
):
    record = _profile_record(user.id, db)
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None and field != "graduation_year":
            continue
        setattr(record, field, csv_list(value) if field == "languages" and value is not None else value.strip() if isinstance(value, str) else value)
    db.commit()
    return _portfolio_data(user, user, db)


@router.get("/users/{user_id}/portfolio")
def get_portfolio(user_id: int, db: Session = Depends(get_db), viewer: User | None = Depends(optional_user)):
    owner = db.get(User, user_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _portfolio_data(owner, viewer, db)


@router.post("/users/me/portfolio/skills", status_code=201)
def add_portfolio_skill(
    data: DeveloperSkillIn, user: User = Depends(current_user), db: Session = Depends(get_db),
):
    skill = DeveloperSkill(
        user_id=user.id, name=data.name.strip(), category=data.category.strip(),
        proficiency=data.proficiency, verified=False,
    )
    db.add(skill)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="That portfolio skill already exists") from None
    db.refresh(skill)
    return {"id": skill.id, "name": skill.name, "category": skill.category, "proficiency": skill.proficiency, "verified": False}


@router.delete("/users/me/portfolio/skills/{skill_id}", status_code=204)
def delete_portfolio_skill(skill_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    skill = db.get(DeveloperSkill, skill_id)
    if skill is None or skill.user_id != user.id:
        raise HTTPException(status_code=404, detail="Portfolio skill not found")
    db.delete(skill)
    db.commit()


@router.post("/users/me/portfolio/projects", status_code=201)
def add_project(
    data: PortfolioProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db),
):
    project = PortfolioProject(
        user_id=user.id, title=data.title.strip(), description=data.description.strip(),
        technologies=csv_list(data.technologies), repository_url=data.repository_url,
        demo_url=data.demo_url,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"id": project.id, "title": project.title}


@router.delete("/users/me/portfolio/projects/{project_id}", status_code=204)
def delete_project(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = db.get(PortfolioProject, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()


@router.post("/users/me/portfolio/credentials", status_code=201)
def add_credential(
    data: ProfileCredentialIn, user: User = Depends(current_user), db: Session = Depends(get_db),
):
    credential = ProfileCredential(
        user_id=user.id, title=data.title.strip(), issuer=data.issuer.strip(),
        evidence_url=data.evidence_url, kind=data.kind,
    )
    db.add(credential)
    db.commit()
    db.refresh(credential)
    return {"id": credential.id, "title": credential.title, "kind": credential.kind}


@router.delete("/users/me/portfolio/credentials/{credential_id}", status_code=204)
def delete_credential(credential_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    credential = db.get(ProfileCredential, credential_id)
    if credential is None or credential.user_id != user.id:
        raise HTTPException(status_code=404, detail="Credential not found")
    db.delete(credential)
    db.commit()


@router.post("/users/me/portfolio/hackathons", status_code=201)
def add_hackathon_history(
    data: HackathonHistoryIn, user: User = Depends(current_user), db: Session = Depends(get_db),
):
    history = HackathonHistory(
        user_id=user.id,
        **{
            key: csv_list(value) if key == "technologies" else value.strip() if isinstance(value, str) else value
            for key, value in data.model_dump().items()
        },
        verified=False,
    )
    db.add(history)
    db.commit()
    db.refresh(history)
    return {"id": history.id, "event_name": history.event_name, "verified": False}


@router.delete("/users/me/portfolio/hackathons/{history_id}", status_code=204)
def delete_hackathon_history(history_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    history = db.get(HackathonHistory, history_id)
    if history is None or history.user_id != user.id:
        raise HTTPException(status_code=404, detail="Hackathon history entry not found")
    db.delete(history)
    db.commit()


def _storage_directory() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    configured = Path(os.getenv("HACKMATE_PRIVATE_UPLOAD_DIR", "instance/private_uploads"))
    path = (configured if configured.is_absolute() else project_root / configured).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


@router.post("/users/me/resume", status_code=201)
async def upload_resume(
    file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    if file.content_type != "application/pdf" or not file.filename or Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail="Upload a PDF resume")
    content = await file.read(MAX_RESUME_BYTES + 1)
    await file.close()
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume must be 5 MB or smaller")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="The uploaded file is not a valid PDF")
    if b"%%EOF" not in content[-2048:]:
        raise HTTPException(status_code=415, detail="The uploaded PDF appears incomplete")
    record = _profile_record(user.id, db)
    storage = _storage_directory()
    storage_key = f"{uuid.uuid4().hex}.pdf"
    target = storage / storage_key
    target.write_bytes(content)
    previous_key = record.resume_storage_key
    record.resume_storage_key = storage_key
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        target.unlink(missing_ok=True)
        raise
    if previous_key and STORAGE_KEY_PATTERN.fullmatch(previous_key):
        (storage / previous_key).unlink(missing_ok=True)
    return {"available": True, "download_url": f"/api/users/{user.id}/resume"}


@router.get("/users/{user_id}/resume")
def download_resume(
    user_id: int, download: bool = False, viewer: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    owner = db.get(User, user_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    record = db.scalar(select(DeveloperProfile).where(DeveloperProfile.user_id == user_id))
    if record is None or not record.resume_storage_key:
        raise HTTPException(status_code=404, detail="Resume not found")
    if not _can_view_private(record, viewer, owner) and not record.resume_visible:
        raise HTTPException(status_code=404, detail="Resume not found")
    if not STORAGE_KEY_PATTERN.fullmatch(record.resume_storage_key):
        raise HTTPException(status_code=404, detail="Resume not found")
    target = _storage_directory() / record.resume_storage_key
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Resume not found")
    return FileResponse(
        target, media_type="application/pdf",
        filename="resume.pdf" if download else None,
        headers={"Content-Disposition": "attachment; filename=\"resume.pdf\"" if download else "inline"},
    )


@router.delete("/users/me/resume", status_code=204)
def delete_resume(user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = db.scalar(select(DeveloperProfile).where(DeveloperProfile.user_id == user.id))
    if record is None or not record.resume_storage_key:
        raise HTTPException(status_code=404, detail="Resume not found")
    key = record.resume_storage_key
    record.resume_storage_key = ""
    db.commit()
    if STORAGE_KEY_PATTERN.fullmatch(key):
        (_storage_directory() / key).unlink(missing_ok=True)


@router.get("/users/{user_id}/github")
def github_public_profile(user_id: int, db: Session = Depends(get_db)):
    owner = db.get(User, user_id)
    record = db.scalar(select(DeveloperProfile).where(DeveloperProfile.user_id == user_id))
    if owner is None or record is None or not record.github_username:
        raise HTTPException(status_code=404, detail="Public GitHub profile is not configured")
    if not record.credentials_visible:
        raise HTTPException(status_code=404, detail="Public portfolio details are hidden")
    username = record.github_username
    try:
        with httpx.Client(timeout=5.0, headers={"Accept": "application/vnd.github+json", "User-Agent": "HackMate"}) as client:
            profile_response = client.get(f"https://api.github.com/users/{username}")
            if profile_response.status_code in {403, 429}:
                raise HTTPException(status_code=503, detail="GitHub API rate limit reached; try again later")
            if profile_response.status_code == 404:
                raise HTTPException(status_code=404, detail="GitHub user was not found")
            profile_response.raise_for_status()
            repo_response = client.get(f"https://api.github.com/users/{username}/repos", params={"sort": "updated", "per_page": 8})
            if repo_response.status_code in {403, 429}:
                raise HTTPException(status_code=503, detail="GitHub API rate limit reached; try again later")
            repo_response.raise_for_status()
            profile = profile_response.json()
            repositories = repo_response.json()
    except HTTPException:
        raise
    except (httpx.TimeoutException, httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Could not retrieve public GitHub data right now") from exc
    return {
        "username": profile["login"],
        "profile_url": profile["html_url"],
        "public_repositories": profile["public_repos"],
        "repositories": [
            {
                "name": repository["name"], "description": repository["description"],
                "url": repository["html_url"], "language": repository["language"],
                "stars": repository["stargazers_count"],
            }
            for repository in repositories if not repository.get("private", False)
        ],
        "source": "GitHub public API",
    }
