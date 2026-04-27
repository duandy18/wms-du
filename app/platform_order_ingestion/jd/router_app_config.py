# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/jd/router_app_config.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.platform_order_ingestion.permissions import (
    require_platform_order_ingestion_read,
    require_platform_order_ingestion_write,
)
from app.user.deps.auth import get_current_user

from .repository import (
    JdAppConfigUpsertInput,
    get_enabled_jd_app_config,
    upsert_current_jd_app_config,
)

router = APIRouter(tags=["oms-jd-app-config"])


def _mask_secret(secret: str | None) -> str:
    value = str(secret or "").strip()
    if not value:
        return ""
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}***{value[-3:]}"


@router.get("/jd/app-config/current")
async def get_jd_app_config_current(
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    require_platform_order_ingestion_read(db, current_user)

    row = await get_enabled_jd_app_config(session)
    if row is None:
        return {
            "ok": True,
            "data": {
                "id": None,
                "client_id": "",
                "client_secret_present": False,
                "client_secret_masked": "",
                "callback_url": "",
                "gateway_url": "https://api.jd.com/routerjson",
                "sign_method": "md5",
                "is_enabled": False,
                "created_at": None,
                "updated_at": None,
            },
        }

    return {
        "ok": True,
        "data": {
            "id": row.id,
            "client_id": row.client_id,
            "client_secret_present": bool(str(row.client_secret or "").strip()),
            "client_secret_masked": _mask_secret(row.client_secret),
            "callback_url": row.callback_url,
            "gateway_url": row.gateway_url,
            "sign_method": row.sign_method,
            "is_enabled": row.is_enabled,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        },
    }


@router.put("/jd/app-config/current")
async def put_jd_app_config_current(
    payload: dict,
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    require_platform_order_ingestion_write(db, current_user)

    """
    约定：
    - 若 client_secret 为空字符串，则沿用原 secret（已有记录时）
    - 若当前无记录，则创建时 client_secret 必填
    """
    client_id = str(payload.get("client_id") or "").strip()
    client_secret_raw = payload.get("client_secret")
    client_secret = str(client_secret_raw or "").strip()
    callback_url = str(payload.get("callback_url") or "").strip()
    gateway_url = str(payload.get("gateway_url") or "https://api.jd.com/routerjson").strip()
    sign_method = str(payload.get("sign_method") or "md5").strip().lower()
    is_enabled = bool(payload.get("is_enabled", True))

    current = await get_enabled_jd_app_config(session)

    try:
        if current is None and not client_secret:
            raise ValueError("client_secret is required when creating jd app config")

        if client_secret:
            secret_to_save = client_secret
        else:
            secret_to_save = current.client_secret if current is not None else None

        row = await upsert_current_jd_app_config(
            session,
            data=JdAppConfigUpsertInput(
                client_id=client_id,
                client_secret=secret_to_save,
                callback_url=callback_url,
                gateway_url=gateway_url,
                sign_method=sign_method,
                is_enabled=is_enabled,
            ),
        )
        await session.commit()
        await session.refresh(row)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        await session.rollback()
        raise

    return {
        "ok": True,
        "data": {
            "id": row.id,
            "client_id": row.client_id,
            "client_secret_present": bool(str(row.client_secret or "").strip()),
            "client_secret_masked": _mask_secret(row.client_secret),
            "callback_url": row.callback_url,
            "gateway_url": row.gateway_url,
            "sign_method": row.sign_method,
            "is_enabled": row.is_enabled,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        },
    }
