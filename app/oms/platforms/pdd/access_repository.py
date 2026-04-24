# app/oms/platforms/pdd/access_repository.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.oms.platforms.models.store_platform_connection import StorePlatformConnection
from app.oms.platforms.models.store_platform_credential import StorePlatformCredential


def _norm_platform(platform: str) -> str:
    value = str(platform or "").strip().lower()
    if not value:
        raise ValueError("platform is required")
    return value


@dataclass(frozen=True)
class CredentialUpsertInput:
    store_id: int
    platform: str
    access_token: str
    expires_at: datetime

    credential_type: str = "oauth"
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    raw_payload_json: Optional[dict] = None
    granted_identity_type: Optional[str] = None
    granted_identity_value: Optional[str] = None
    granted_identity_display: Optional[str] = None


@dataclass(frozen=True)
class ConnectionEnsureInput:
    store_id: int
    platform: str


@dataclass(frozen=True)
class ConnectionUpsertInput:
    store_id: int
    platform: str

    auth_source: Optional[str] = None
    connection_status: Optional[str] = None
    credential_status: Optional[str] = None
    reauth_required: Optional[bool] = None
    pull_ready: Optional[bool] = None
    status: Optional[str] = None
    status_reason: Optional[str] = None
    last_authorized_at: Optional[datetime] = None
    last_pull_checked_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None


async def get_credential_by_store_platform(
    session: AsyncSession,
    *,
    store_id: int,
    platform: str,
) -> Optional[StorePlatformCredential]:
    stmt = (
        sa.select(StorePlatformCredential)
        .where(
            StorePlatformCredential.store_id == store_id,
            StorePlatformCredential.platform == _norm_platform(platform),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_credential_by_store_platform(
    session: AsyncSession,
    *,
    data: CredentialUpsertInput,
) -> StorePlatformCredential:
    platform = _norm_platform(data.platform)

    row = await get_credential_by_store_platform(
        session,
        store_id=data.store_id,
        platform=platform,
    )

    payload = data.raw_payload_json if isinstance(data.raw_payload_json, dict) else {}

    if row is None:
        row = StorePlatformCredential(
            store_id=data.store_id,
            platform=platform,
            credential_type=data.credential_type,
            access_token=data.access_token,
            refresh_token=data.refresh_token,
            expires_at=data.expires_at,
            scope=data.scope,
            raw_payload_json=payload,
            granted_identity_type=data.granted_identity_type,
            granted_identity_value=data.granted_identity_value,
            granted_identity_display=data.granted_identity_display,
        )
        session.add(row)
        await session.flush()
        return row

    row.credential_type = data.credential_type
    row.access_token = data.access_token
    row.refresh_token = data.refresh_token
    row.expires_at = data.expires_at
    row.scope = data.scope
    row.raw_payload_json = payload
    row.granted_identity_type = data.granted_identity_type
    row.granted_identity_value = data.granted_identity_value
    row.granted_identity_display = data.granted_identity_display

    await session.flush()
    return row


async def get_connection_by_store_platform(
    session: AsyncSession,
    *,
    store_id: int,
    platform: str,
) -> Optional[StorePlatformConnection]:
    stmt = (
        sa.select(StorePlatformConnection)
        .where(
            StorePlatformConnection.store_id == store_id,
            StorePlatformConnection.platform == _norm_platform(platform),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def ensure_connection_row(
    session: AsyncSession,
    *,
    data: ConnectionEnsureInput,
) -> StorePlatformConnection:
    platform = _norm_platform(data.platform)

    row = await get_connection_by_store_platform(
        session,
        store_id=data.store_id,
        platform=platform,
    )
    if row is not None:
        return row

    row = StorePlatformConnection(
        store_id=data.store_id,
        platform=platform,
    )
    session.add(row)
    await session.flush()
    return row


async def upsert_connection_by_store_platform(
    session: AsyncSession,
    *,
    data: ConnectionUpsertInput,
) -> StorePlatformConnection:
    row = await ensure_connection_row(
        session,
        data=ConnectionEnsureInput(
            store_id=data.store_id,
            platform=data.platform,
        ),
    )

    if data.auth_source is not None:
        row.auth_source = data.auth_source
    if data.connection_status is not None:
        row.connection_status = data.connection_status
    if data.credential_status is not None:
        row.credential_status = data.credential_status
    if data.reauth_required is not None:
        row.reauth_required = data.reauth_required
    if data.pull_ready is not None:
        row.pull_ready = data.pull_ready
    if data.status is not None:
        row.status = data.status
    if data.status_reason is not None:
        row.status_reason = data.status_reason
    if data.last_authorized_at is not None:
        row.last_authorized_at = data.last_authorized_at
    if data.last_pull_checked_at is not None:
        row.last_pull_checked_at = data.last_pull_checked_at
    if data.last_error_at is not None:
        row.last_error_at = data.last_error_at

    await session.flush()
    return row
