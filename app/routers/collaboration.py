from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    ChatMessage, Notification, Review, Task, Team, TeamMember, User,
)
from app.schemas import MessageIn, ReviewIn, TaskIn, TaskUpdate
from app.security import current_user
from app.services.common import is_team_member, profile_data, require_team_member


router = APIRouter(tags=["Workspace, chat, and reviews"])


def task_data(task: Task, db: Session):
    assignee = db.get(User, task.assignee_id) if task.assignee_id else None
    return {
        "id": task.id, "team_id": task.team_id, "title": task.title, "description": task.description,
        "status": task.status, "priority": task.priority, "due_date": task.due_date,
        "assignee_id": task.assignee_id, "assignee_name": assignee.name if assignee else None,
        "creator_id": task.creator_id, "created_at": task.created_at.isoformat(),
    }


@router.get("/teams/{team_id}/tasks")
def list_tasks(team_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_team_member(team_id, user, db)
    rows = db.scalars(select(Task).where(Task.team_id == team_id).order_by(Task.created_at.desc())).all()
    return [task_data(task, db) for task in rows]


@router.post("/teams/{team_id}/tasks", status_code=201)
def create_task(
    team_id: int, data: TaskIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    require_team_member(team_id, user, db)
    if data.assignee_id is not None and not is_team_member(team_id, data.assignee_id, db):
        raise HTTPException(status_code=422, detail="Assignee must be a member of this team")
    task = Task(team_id=team_id, creator_id=user.id, **data.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task_data(task, db)


@router.patch("/teams/{team_id}/tasks/{task_id}")
def update_task(
    team_id: int, task_id: int, data: TaskUpdate,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    require_team_member(team_id, user, db)
    task = db.get(Task, task_id)
    if task is None or task.team_id != team_id:
        raise HTTPException(status_code=404, detail="Task not found")
    changes = data.model_dump(exclude_unset=True)
    if changes.get("assignee_id") is not None and not is_team_member(team_id, changes["assignee_id"], db):
        raise HTTPException(status_code=422, detail="Assignee must be a member of this team")
    for field, value in changes.items():
        setattr(task, field, value)
    db.commit()
    return task_data(task, db)


@router.get("/teams/{team_id}/workspace")
def workspace(team_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_team_member(team_id, user, db)
    tasks = db.scalars(select(Task).where(Task.team_id == team_id)).all()
    total = len(tasks)
    complete = sum(task.status == "Done" for task in tasks)
    return {
        "team_id": team_id, "tasks": [task_data(task, db) for task in tasks],
        "progress_percent": round(complete / total * 100) if total else 0,
        "completed_tasks": complete, "total_tasks": total,
    }


@router.get("/teams/{team_id}/messages")
def list_messages(team_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_team_member(team_id, user, db)
    rows = db.scalars(
        select(ChatMessage).where(ChatMessage.team_id == team_id).order_by(ChatMessage.created_at.asc()).limit(300)
    ).all()
    return [
        {
            "id": row.id, "team_id": row.team_id, "sender_id": row.sender_id,
            "sender_name": db.get(User, row.sender_id).name, "content": row.content,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.post("/teams/{team_id}/messages", status_code=201)
def send_message(
    team_id: int, data: MessageIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    require_team_member(team_id, user, db)
    message = ChatMessage(team_id=team_id, sender_id=user.id, content=data.content.strip())
    db.add(message)
    db.commit()
    db.refresh(message)
    return {
        "id": message.id, "team_id": team_id, "sender_id": user.id, "sender_name": user.name,
        "content": message.content, "created_at": message.created_at.isoformat(),
    }


@router.post("/teams/{team_id}/reviews", status_code=201)
def create_review(
    team_id: int, data: ReviewIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    require_team_member(team_id, user, db)
    if data.reviewee_id == user.id or not is_team_member(team_id, data.reviewee_id, db):
        raise HTTPException(status_code=422, detail="Reviews must be for another member of your team")
    review = Review(
        team_id=team_id, reviewer_id=user.id, reviewee_id=data.reviewee_id,
        rating=data.rating,
        communication_rating=data.communication_rating or data.rating,
        reliability_rating=data.reliability_rating or data.rating,
        teamwork_rating=data.teamwork_rating or data.rating,
        feedback=data.feedback.strip(),
    )
    db.add(review)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if "UNIQUE constraint failed" in str(error.orig):
            raise HTTPException(status_code=409, detail="You have already reviewed this collaborator") from None
        raise
    db.refresh(review)
    return {"id": review.id, "rating": review.rating, "message": "Review submitted"}


@router.get("/users/{user_id}/reviews")
def get_reviews(user_id: int, db: Session = Depends(get_db)):
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    rows = db.scalars(select(Review).where(Review.reviewee_id == user_id).order_by(Review.created_at.desc())).all()
    average = db.scalar(select(func.avg(Review.rating)).where(Review.reviewee_id == user_id))
    dimensions = {}
    for field in ("communication_rating", "reliability_rating", "teamwork_rating"):
        values = [getattr(row, field) or row.rating for row in rows]
        dimensions[field.removesuffix("_rating")] = {
            "average": round(sum(values) / len(values), 1) if values else None,
            "count": len(values),
        }
    return {
        "user_id": user_id, "average_rating": round(average, 1) if average is not None else None,
        "count": len(rows), "dimensions": dimensions,
        "reviews": [
            {
                "id": row.id, "team_id": row.team_id, "reviewer": db.get(User, row.reviewer_id).name,
                "rating": row.rating,
                "communication_rating": row.communication_rating or row.rating,
                "reliability_rating": row.reliability_rating or row.rating,
                "teamwork_rating": row.teamwork_rating or row.rating,
                "feedback": row.feedback, "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }


@router.get("/notifications")
def list_notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(100)
    ).all()
    return [
        {"id": row.id, "message": row.message, "read": row.read, "created_at": row.created_at.isoformat()}
        for row in rows
    ]


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.read = True
    db.commit()
    return {"id": notification.id, "read": True}
