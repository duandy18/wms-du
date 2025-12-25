# app/api/routers/user_routes_password.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.services.user_service import AuthorizationError, NotFoundError, UserService

from app.api.routers.user_schemas import PasswordChangeIn


def register(router: APIRouter) -> None:
    @router.post("/change-password")
    def change_password(
        body: PasswordChangeIn,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        svc = UserService(db)
        try:
            svc.change_password(
                current_user.id,
                old_password=body.old_password,
                new_password=body.new_password,
            )
            return {"ok": True}
        except AuthorizationError:
            raise HTTPException(status_code=403, detail="旧密码错误")
        except NotFoundError:
            raise HTTPException(status_code=404, detail="用户不存在")
