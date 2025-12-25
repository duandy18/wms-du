# app/services/user_crud.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.security import get_password_hash, verify_password
from app.models.role import Role
from app.models.user import User, user_roles
from app.services.user_errors import AuthorizationError, DuplicateUserError, NotFoundError


def create_user(
    db: Session,
    *,
    username: str,
    password: str,
    primary_role_id: int,
    full_name: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    extra_role_ids: Optional[List[int]] = None,
) -> User:
    existed = db.query(User).filter(User.username == username).first()
    if existed:
        raise DuplicateUserError("用户名已存在")

    primary_role = db.query(Role).filter(Role.id == primary_role_id).first()
    if not primary_role:
        raise NotFoundError("主角色不存在")

    user = User(
        username=username.strip(),
        password_hash=get_password_hash(password),
        primary_role_id=primary_role_id,
        full_name=(full_name or "").strip() or None,
        phone=(phone or "").strip() or None,
        email=(email or "").strip() or None,
    )
    db.add(user)
    db.flush()

    if extra_role_ids:
        for rid in extra_role_ids:
            db.execute(user_roles.insert().values(user_id=user.id, role_id=rid))

    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    *,
    user_id: int,
    full_name: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    primary_role_id: Optional[int] = None,
    extra_role_ids: Optional[List[int]] = None,
    is_active: Optional[bool] = None,
) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise NotFoundError("用户不存在")

    if full_name is not None:
        user.full_name = full_name or None
    if phone is not None:
        user.phone = phone or None
    if email is not None:
        user.email = email or None
    if is_active is not None:
        user.is_active = bool(is_active)

    if primary_role_id is not None:
        role = db.query(Role).filter(Role.id == primary_role_id).first()
        if not role:
            raise NotFoundError("主角色不存在")
        user.primary_role_id = primary_role_id

    if extra_role_ids is not None:
        db.execute(user_roles.delete().where(user_roles.c.user_id == user_id))
        for rid in extra_role_ids:
            db.execute(user_roles.insert().values(user_id=user_id, role_id=rid))

    db.commit()
    db.refresh(user)
    return user


def change_password(db: Session, *, user_id: int, old_password: str, new_password: str) -> None:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise NotFoundError("用户不存在")
    if not verify_password(old_password, user.password_hash):
        raise AuthorizationError("旧密码不正确")

    user.password_hash = get_password_hash(new_password)
    db.commit()
