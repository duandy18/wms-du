# app/routers/users.py
from typing import TYPE_CHECKING, Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.schemas import UserCreate, UserOut, UserUpdate

# Dependency-annotated DB session
DB = Annotated[Session, Depends(get_db)]

# If you prefer explicit model type annotations elsewhere:
if TYPE_CHECKING:
    UserT = models.User
else:
    UserT = models.User

# Mounted in app.main with a prefix, e.g. prefix="/users"
router = APIRouter()


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    response_model_exclude_none=True,
)
def create_user(payload: UserCreate, db: DB) -> UserOut:
    username = payload.username
    exists = db.execute(
        select(models.User).where(models.User.username == username)
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="username already exists")

    user = models.User(username=username)

    # Optional fields
    if getattr(payload, "email", None) is not None:
        user_any = cast(Any, user)
        user_any.email = payload.email

    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: DB) -> UserOut:
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return UserOut.model_validate(user)


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: DB,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[UserOut]:
    rows = db.execute(select(models.User).offset(skip).limit(limit)).scalars().all()
    return [UserOut.model_validate(r) for r in rows]


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: DB) -> UserOut:
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    if getattr(payload, "email", None) is not None:
        user_any = cast(Any, user)
        user_any.email = payload.email

    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: DB) -> None:
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    db.delete(user)
    db.commit()
