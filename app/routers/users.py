# app/routers/users.py
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.schemas import UserCreate, UserOut, UserUpdate

DB = Annotated[Session, Depends(get_db)]
# 不在这里加 prefix;由 apps/api/main.py 统一挂载 prefix="/users"
router = APIRouter()


def _has_attr(model_cls: type, name: str) -> bool:
    return hasattr(model_cls, name)


@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    response_model_exclude_none=True,
)
def create_user(payload: UserCreate, db: DB):
    username: Any = payload.username
    # 查重: 只查 username
    exists = db.execute(
        select(models.User).where(models.User.username == username)
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="username already exists")

    user = models.User(username=username)

    # 可选 email: 仅当模型有该列且 payload 提供时才设置
    if _has_attr(models.User, "email"):
        email_val: Any = getattr(payload, "email", None)
        if email_val is not None:
            user_any = cast(Any, user)
            user_any.email = email_val  # 不直接写 user.email

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get(
    "",
    response_model=list[UserOut],
    response_model_exclude_none=True,
)
def list_users(
    db: DB,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    return db.execute(select(models.User).offset(skip).limit(limit)).scalars().all()


@router.get(
    "/{user_id}",
    response_model=UserOut,
    response_model_exclude_none=True,
)
def get_user(user_id: int, db: DB):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@router.put(
    "/{user_id}",
    response_model=UserOut,
    response_model_exclude_none=True,
)
def update_user(user_id: int, payload: UserUpdate, db: DB):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")

    # 改用户名: 先查重
    new_username: Any = getattr(payload, "username", None)
    if new_username is not None and new_username != user.username:
        dup = db.execute(
            select(models.User).where(models.User.username == new_username)
        ).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=409, detail="username already exists")
        user.username = new_username

    # 改邮箱: 仅当模型有该列且 payload 提供时
    if _has_attr(models.User, "email"):
        new_email: Any = getattr(payload, "email", None)
        if new_email is not None:
            user_any = cast(Any, user)
            user_any.email = new_email  # 不直接写 user.email

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_user(user_id: int, db: DB):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    db.delete(user)
    db.commit()
    # 204: no body
