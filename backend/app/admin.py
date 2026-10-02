from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_admin_user
from app.db import Document, LoginEvent, User, get_db


router = APIRouter()


class UserActiveUpdate(BaseModel):
    is_active: bool


def _user_account(user: User, document_count: int) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
        "is_active": user.is_active,
        "document_count": document_count,
    }


@router.get("/admin/users")
def list_users(
    session: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    document_count = (
        select(func.count(Document.id))
        .where(Document.user_id == User.id)
        .scalar_subquery()
    )
    rows = session.execute(
        select(User, document_count.label("document_count"))
        .order_by(User.created_at.desc(), User.id.desc())
    ).all()
    return [
        _user_account(user, count)
        for user, count in rows
    ]


@router.get("/admin/login-events")
def list_login_events(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    events = session.scalars(
        select(LoginEvent)
        .order_by(LoginEvent.created_at.desc(), LoginEvent.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": event.id,
            "email": event.email,
            "success": event.success,
            "created_at": event.created_at,
        }
        for event in events
    ]


@router.patch("/admin/users/{user_id}")
def update_user(
    user_id: int,
    update: UserActiveUpdate,
    session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and not update.is_active:
        raise HTTPException(
            status_code=400,
            detail="Admins cannot disable their own account",
        )

    user.is_active = update.is_active
    session.commit()
    document_count = session.scalar(
        select(func.count(Document.id)).where(Document.user_id == user.id)
    )
    return _user_account(user, document_count or 0)
