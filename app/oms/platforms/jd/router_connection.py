# app/oms/platforms/jd/router_connection.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session

from .repository import (
    get_connection_by_store_platform,
    get_credential_by_store_platform,
)

router = APIRouter(tags=["oms-jd-connection"])


@router.get("/stores/{store_id}/jd/connection")
async def get_store_jd_connection(
    store_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        credential = await get_credential_by_store_platform(
            session,
            store_id=store_id,
            platform="jd",
        )
        connection = await get_connection_by_store_platform(
            session,
            store_id=store_id,
            platform="jd",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to load jd connection: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "store_id": store_id,
            "platform": "jd",
            "credential_present": credential is not None,
            "credential_expires_at": credential.expires_at.isoformat()
            if credential and credential.expires_at
            else None,
            "granted_identity_type": credential.granted_identity_type
            if credential
            else None,
            "granted_identity_value": credential.granted_identity_value
            if credential
            else None,
            "granted_identity_display": credential.granted_identity_display
            if credential
            else None,
            "auth_source": connection.auth_source if connection else "none",
            "connection_status": connection.connection_status
            if connection
            else "not_connected",
            "credential_status": connection.credential_status
            if connection
            else "missing",
            "reauth_required": bool(connection.reauth_required)
            if connection
            else False,
            "pull_ready": bool(connection.pull_ready) if connection else False,
            "status": connection.status if connection else "not_connected",
            "status_reason": connection.status_reason if connection else None,
            "last_authorized_at": connection.last_authorized_at.isoformat()
            if connection and connection.last_authorized_at
            else None,
            "last_pull_checked_at": connection.last_pull_checked_at.isoformat()
            if connection and connection.last_pull_checked_at
            else None,
            "last_error_at": connection.last_error_at.isoformat()
            if connection and connection.last_error_at
            else None,
        },
    }
