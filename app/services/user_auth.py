# app/services/user_auth.py
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import create_access_token, decode_access_token, verify_password
from app.models.user import User


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_token_for_user(user: User, *, expires_in: Optional[int] = None) -> str:
    payload = {"sub": user.username}
    return create_access_token(data=payload, expires_minutes=expires_in)


def get_user_from_token(db: Session, token: str) -> Optional[User]:
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    return db.query(User).filter(User.username == payload["sub"]).first()
