from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserInterest, UserSkill
from app.schemas import LoginIn, ProfileIn, RegisterIn
from app.security import create_token, current_user, hash_password, verify_password
from app.services.common import csv_list, profile_data


router = APIRouter(tags=["Authentication and profiles"])


@router.post("/auth/register", status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(email=email, name=data.name.strip(), password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"access_token": create_token(user.id), "token_type": "bearer", "user": profile_data(user, db, include_email=True)}


@router.post("/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return {"access_token": create_token(user.id), "token_type": "bearer", "user": profile_data(user, db, include_email=True)}


@router.get("/auth/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return profile_data(user, db, include_email=True)


@router.post("/auth/logout")
def logout(user: User = Depends(current_user)):
    return {"message": "Logged out. Remove the access token from this device."}


@router.get("/users/{user_id}")
def get_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return profile_data(user, db)


@router.put("/users/me/profile")
def update_profile(
    data: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    for field in (
        "name", "college", "department", "photo_url", "experience", "preferred_role",
        "availability", "bio", "project_experience",
    ):
        setattr(user, field, getattr(data, field).strip())
    db.query(UserSkill).filter(UserSkill.user_id == user.id).delete()
    db.query(UserInterest).filter(UserInterest.user_id == user.id).delete()
    db.add_all([UserSkill(user_id=user.id, name=name) for name in csv_list(data.skills).split(",") if name])
    db.add_all([UserInterest(user_id=user.id, name=name) for name in csv_list(data.interests).split(",") if name])
    db.commit()
    return profile_data(user, db, include_email=True)
