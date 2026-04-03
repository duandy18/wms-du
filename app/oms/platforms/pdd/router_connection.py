# app/oms/platforms/pdd/router_connection.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session

from .access_repository import (
    get_connection_by_store_platform,
    get_credential_by_store_platform,
)

router = APIRouter(tags=["oms-pdd-connection"])


@router.get("/stores/{store_id}/pdd/connection")
async def get_store_pdd_connection(
    store_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    读取店铺 × 拼多多当前 connection 视图。

    说明：
    - credential 是授权材料当前态
    - connection 是 OMS 当前裁决状态
    """
    platform = "pdd"

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
                "platform": platform,
                "store_id": store_id,
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
                "credential": None,
            },
        }

    credential_data = None
    if credential is not None:
        credential_data = {
            "credential_type": credential.credential_type,
            "access_token_present": bool(str(credential.access_token or "").strip()),
            "refresh_token_present": bool(str(credential.refresh_token or "").strip()),
            "expires_at": credential.expires_at.isoformat()
            if credential.expires_at
            else None,
            "scope": credential.scope,
            "granted_identity_type": credential.granted_identity_type,
            "granted_identity_value": credential.granted_identity_value,
            "granted_identity_display": credential.granted_identity_display,
            "updated_at": credential.updated_at.isoformat()
            if credential.updated_at
            else None,
        }

    return {
        "ok": True,
        "data": {
            "platform": platform,
            "store_id": store_id,
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
            "status_reason": (
                connection.status_reason if connection else "authorization_missing"
            ),
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
            "credential": credential_data,
        },
    }
