# app/oms/platforms/taobao/router_connection.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.db.deps import get_db
from app.oms.routers import stores as stores_router

from .repository import (
    get_connection_by_store_platform,
    get_credential_by_store_platform,
)

router = APIRouter(tags=["oms-taobao-connection"])


@router.get("/stores/{store_id}/taobao/connection")
async def get_store_taobao_connection(
    store_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """
    淘宝接入状态读取口（新主线）。

    当前返回：
    - store_id / platform
    - credentials 基础存在性与过期信息
    - connection 当前裁决状态
    - 授权返回自带的基础身份线索

    说明：
    - 第一版先直接读新两张表
    - 先不复用旧 stores_platform_auth.py
    """
    stores_router._check_perm(db, current_user, ["config.store.read"])

    platform = "taobao"

    connection = await get_connection_by_store_platform(
        session,
        store_id=store_id,
        platform=platform,
    )
    credential = await get_credential_by_store_platform(
        session,
        store_id=store_id,
        platform=platform,
    )

    if connection is None and credential is None:
        return {
            "ok": True,
            "data": {
                "store_id": store_id,
                "platform": platform,
                "credential_present": False,
                "credential_expires_at": None,
                "granted_identity_type": None,
                "granted_identity_value": None,
                "granted_identity_display": None,
                "auth_source": "none",
                "connection_status": "not_connected",
                "credential_status": "missing",
                "reauth_required": False,
                "pull_ready": False,
                "status": "not_connected",
                "status_reason": "authorization_missing",
                "last_authorized_at": None,
                "last_pull_checked_at": None,
                "last_error_at": None,
            },
        }

    return {
        "ok": True,
        "data": {
            "store_id": store_id,
            "platform": platform,
            "credential_present": credential is not None,
            "credential_expires_at": (
                credential.expires_at.isoformat() if credential and credential.expires_at else None
            ),
            "granted_identity_type": (
                credential.granted_identity_type if credential else None
            ),
            "granted_identity_value": (
                credential.granted_identity_value if credential else None
            ),
            "granted_identity_display": (
                credential.granted_identity_display if credential else None
            ),
            "auth_source": connection.auth_source if connection else "none",
            "connection_status": (
                connection.connection_status if connection else "not_connected"
            ),
            "credential_status": (
                connection.credential_status if connection else "missing"
            ),
            "reauth_required": (
                bool(connection.reauth_required) if connection else False
            ),
            "pull_ready": bool(connection.pull_ready) if connection else False,
            "status": connection.status if connection else "not_connected",
            "status_reason": connection.status_reason if connection else "authorization_missing",
            "last_authorized_at": (
                connection.last_authorized_at.isoformat()
                if connection and connection.last_authorized_at
                else None
            ),
            "last_pull_checked_at": (
                connection.last_pull_checked_at.isoformat()
                if connection and connection.last_pull_checked_at
                else None
            ),
            "last_error_at": (
                connection.last_error_at.isoformat()
                if connection and connection.last_error_at
                else None
            ),
        },
    }
