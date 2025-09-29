# app/authz.py
from __future__ import annotations

from typing import Set
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User

def get_current_user() -> User:
    """
    占位函数：请替换为你项目里真实的登录态解析。
    例如：从 Authorization: Bearer <token> 解出 user_id 并加载 User。
    现在默认抛 401，便于先验证未登录分支。
    """
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

def _collect_permission_codes(user: User) -> Set[str]:
    codes: Set[str] = set()
    for r in getattr(user, "roles", []) or []:
        for p in getattr(r, "permissions", []) or []:
            codes.add(p.code)
    return codes

def require_perms(*needed: str):
    """
    用法：
        @router.get("/x")
        def x(user = Depends(require_perms("purchase:view"))): ...
    """
    def dep(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        user_codes = _collect_permission_codes(user)
        missing = [c for c in needed if c not in user_codes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"missing_permissions": missing},
            )
        return user
    return dep
