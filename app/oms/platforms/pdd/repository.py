# app/oms/platforms/pdd/repository.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pdd_app_config import PddAppConfig

from .settings import DEFAULT_PDD_API_BASE_URL, DEFAULT_PDD_SIGN_METHOD


@dataclass(frozen=True)
class PddAppConfigUpsertInput:
    client_id: str
    redirect_uri: str

    client_secret: Optional[str] = None
    api_base_url: str = DEFAULT_PDD_API_BASE_URL
    sign_method: str = DEFAULT_PDD_SIGN_METHOD
    is_enabled: bool = True


async def get_enabled_pdd_app_configs(
    session: AsyncSession,
) -> list[PddAppConfig]:
    stmt = (
        sa.select(PddAppConfig)
        .where(PddAppConfig.is_enabled.is_(True))
        .order_by(PddAppConfig.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_enabled_pdd_app_config(
    session: AsyncSession,
) -> Optional[PddAppConfig]:
    rows = await get_enabled_pdd_app_configs(session)
    if not rows:
        return None
    if len(rows) > 1:
        raise ValueError("multiple enabled pdd app configs found")
    return rows[0]


async def require_enabled_pdd_app_config(
    session: AsyncSession,
) -> PddAppConfig:
    row = await get_enabled_pdd_app_config(session)
    if row is None:
        raise ValueError("enabled pdd app config not found")
    return row


async def upsert_current_pdd_app_config(
    session: AsyncSession,
    *,
    data: PddAppConfigUpsertInput,
) -> PddAppConfig:
    client_id = str(data.client_id or "").strip()
    client_secret = str(data.client_secret or "").strip()
    redirect_uri = str(data.redirect_uri or "").strip()
    api_base_url = str(data.api_base_url or "").strip()
    sign_method = str(data.sign_method or "").strip().lower()

    if not client_id:
        raise ValueError("client_id is required")
    if not client_secret:
        raise ValueError("client_secret is required")
    if not redirect_uri:
        raise ValueError("redirect_uri is required")
    if not api_base_url:
        raise ValueError("api_base_url is required")
    if sign_method not in {"md5"}:
        raise ValueError(f"unsupported sign_method: {sign_method!r}")

    row = await get_enabled_pdd_app_config(session)

    if row is None:
        row = PddAppConfig(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            api_base_url=api_base_url,
            sign_method=sign_method,
            is_enabled=bool(data.is_enabled),
        )
        session.add(row)
        await session.flush()
        return row

    row.client_id = client_id
    row.client_secret = client_secret
    row.redirect_uri = redirect_uri
    row.api_base_url = api_base_url
    row.sign_method = sign_method
    row.is_enabled = bool(data.is_enabled)

    await session.flush()
    return row
