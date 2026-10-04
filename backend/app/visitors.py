from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import User, get_db


def get_visitor_user(
    visitor_id: str | None = Header(default=None, alias="X-Visitor-ID"),
    session: Session = Depends(get_db),
) -> User:
    if visitor_id is None:
        raise HTTPException(status_code=400, detail="Visitor ID is required")

    try:
        normalized_id = str(UUID(visitor_id))
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid visitor ID") from error

    email = f"anonymous-{normalized_id}@visitor.invalid"
    user = session.scalar(select(User).where(User.email == email))
    if user is not None:
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Workspace is disabled")
        return user

    user = User(email=email, password_hash="!anonymous!")
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            raise
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Workspace is disabled")

    return user
