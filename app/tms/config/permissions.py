# app/tms/config/permissions.py
# 分拆说明：
# - 本文件统一承载 TMS / TransportConfig 子域权限校验；
# - providers 与 warehouse_provider_bindings 统一从此处导入，避免继续依赖旧 routers helper。
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.user_service import AuthorizationError, UserService


def check_config_perm(db: Session, current_user, required: list[str]) -> None:
    svc = UserService(db)
    try:
        svc.check_permission(current_user, required)
    except AuthorizationError:
        raise HTTPException(status_code=403, detail="Not authorized.")
