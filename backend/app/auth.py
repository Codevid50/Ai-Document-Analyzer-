import os
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import LoginEvent, User, get_db


load_dotenv()
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise ValueError("JWT_SECRET is not set in the environment.")

password_hasher = PasswordHasher()
router = APIRouter()


class Credentials(BaseModel):
    email: str
    password: str


class RegistrationCredentials(Credentials):
    password: str = Field(min_length=8)


def create_access_token(user_id: int) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    return jwt.encode(
        {"sub": str(user_id), "exp": expires_at},
        JWT_SECRET,
        algorithm="HS256",
    )


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(
    credentials: RegistrationCredentials,
    session: Session = Depends(get_db),
):
    email = credentials.email.strip().lower()
    if email == "legacy-data@invalid.local":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=email,
        password_hash=password_hasher.hash(credentials.password),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        if session.scalar(select(User.id).where(User.email == email)) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        raise

    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
    }


@router.post("/auth/login")
def login(
    credentials: Credentials,
    session: Session = Depends(get_db),
):
    email = credentials.email.strip().lower()
    user = session.scalar(select(User).where(User.email == email))
    password_valid = False
    if user is not None and user.is_active:
        try:
            password_valid = password_hasher.verify(
                user.password_hash,
                credentials.password,
            )
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            password_valid = False

    login_succeeded = user is not None and user.is_active and password_valid
    session.add(
        LoginEvent(
            user_id=user.id if user is not None else None,
            email=email,
            success=login_succeeded,
        )
    )
    if not login_succeeded:
        session.commit()
        raise _invalid_credentials()

    user.last_login_at = datetime.now(timezone.utc)
    session.commit()
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
    }


def get_current_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_db),
) -> User:
    if authorization is None:
        raise _invalid_credentials()

    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        raise _invalid_credentials()

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise _invalid_credentials()

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise _invalid_credentials()
    return user


def _is_admin(user: User) -> bool:
    admin_emails = {
        email.strip().lower()
        for email in os.getenv("ADMIN_EMAILS", "").split(",")
        if email.strip()
    }
    return user.email.lower() in admin_emails


def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if not _is_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


@router.get("/auth/me")
def read_current_user(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "is_admin": _is_admin(user)}
