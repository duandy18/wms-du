# app/user/routers/user_routes_me.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.user.contracts.navigation import MyNavigationOut
from app.user.deps.auth import get_current_user
from app.user.services.user_navigation import UserNavigationService
from app.user.services.user_service import UserService


def register(router: APIRouter) -> None:
    @router.get("/me")
    def get_me(
        current_user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        svc = UserService(db)
        permissions = svc.get_user_permissions(current_user)

        user_id = getattr(current_user, "id", None)
        username = getattr(current_user, "username", None)

        return {
            "id": user_id,
            "username": username,
            "permissions": permissions,
        }

    @router.get("/me/navigation", response_model=MyNavigationOut)
    def get_my_navigation(
        current_user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        svc = UserNavigationService(db)
        return svc.get_my_navigation(current_user)
