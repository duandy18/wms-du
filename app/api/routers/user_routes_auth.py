# app/api/routers/user_routes_auth.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.token import Token
from app.schemas.user import UserLogin
from app.services.user_service import UserService

from app.api.routers.user_helpers import token_expires_in_seconds


def register(router: APIRouter) -> None:
    @router.post("/login", response_model=Token, status_code=200)
    def login(
        body: UserLogin,
        db: Session = Depends(get_db),
    ):
        svc = UserService(db)

        user = svc.authenticate_user(body.username, body.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        token = svc.create_token_for_user(user)
        return Token(access_token=token, token_type="bearer", expires_in=token_expires_in_seconds())
