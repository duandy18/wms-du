# app/api/routers/user_routes_me.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.role import Role
from app.services.user_service import UserService


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

        roles: list[dict] = []

        if user_id is not None:
            rows = db.execute(
                text(
                    """
                    SELECT r.id, r.name
                      FROM roles r
                      JOIN user_roles ur ON ur.role_id = r.id
                     WHERE ur.user_id = :uid
                    """
                ),
                {"uid": user_id},
            ).fetchall()
            roles = [{"id": rid, "name": name} for rid, name in rows]

        primary_role_id = getattr(current_user, "primary_role_id", None)
        if primary_role_id:
            primary = db.query(Role).filter(Role.id == primary_role_id).first()
            if primary:
                info = {"id": primary.id, "name": primary.name}
                if info not in roles:
                    roles.insert(0, info)

        return {
            "id": user_id,
            "username": username,
            "roles": roles,
            "permissions": permissions,
        }
