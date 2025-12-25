# app/services/user_permissions.py
from __future__ import annotations

from typing import Any, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.permission import Permission
from app.models.role import role_permissions
from app.services.user_errors import AuthorizationError


def get_user_permissions(db: Session, user: Any) -> List[str]:
    if not user:
        return []

    perms_attr = getattr(user, "permissions", None)
    if perms_attr:
        try:
            return list(dict.fromkeys([str(x) for x in perms_attr if x]))
        except TypeError:
            pass

    if getattr(user, "id", None) is None:
        return []

    role_ids = set()

    if getattr(user, "primary_role_id", None):
        role_ids.add(int(user.primary_role_id))

    rows = db.execute(
        text("SELECT role_id FROM user_roles WHERE user_id = :uid"),
        {"uid": user.id},
    ).fetchall()
    for (rid,) in rows:
        role_ids.add(int(rid))

    if not role_ids:
        return []

    rows = (
        db.query(Permission.name)
        .join(role_permissions, Permission.id == role_permissions.c.permission_id)
        .filter(role_permissions.c.role_id.in_(role_ids))
        .all()
    )

    out: List[str] = []
    seen = set()

    for (name,) in rows:
        if name not in seen:
            seen.add(name)
            out.append(name)

    return out


def check_permission(db: Session, user: Any, required: List[str], *, any_of: bool = True) -> bool:
    perms = set(get_user_permissions(db, user))
    req = set(required)

    if any_of:
        ok = bool(perms & req)
    else:
        ok = req.issubset(perms)

    if not ok:
        raise AuthorizationError("你没有访问该资源的权限")

    return True
