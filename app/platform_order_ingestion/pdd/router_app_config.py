# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/pdd/router_app_config.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.platform_order_ingestion.permissions import (
    require_platform_order_ingestion_read,
    require_platform_order_ingestion_write,
)

from .repository import (
    PddAppConfigUpsertInput,
    get_enabled_pdd_app_config,
    upsert_current_pdd_app_config,
)
from .settings import (
    DEFAULT_PDD_API_BASE_URL,
    DEFAULT_PDD_SIGN_METHOD,
)

router = APIRouter(tags=["oms-pdd-app-config"])


def _mask_secret(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 6:
        return "*" * len(text)
    return f"{text[:3]}{'*' * (len(text) - 6)}{text[-3:]}"


@router.get("/pdd/app-config/current")
async def get_current_pdd_app_config(
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """
    读取当前启用中的拼多多系统配置。
    """
    require_platform_order_ingestion_read(db, current_user)

    try:
        row = await get_enabled_pdd_app_config(session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to load current pdd app config: {exc}",
        ) from exc

    if row is None:
        return {
            "ok": True,
            "data": {
                "id": None,
                "client_id": "",
                "client_secret_present": False,
                "client_secret_masked": "",
                "redirect_uri": "",
                "api_base_url": DEFAULT_PDD_API_BASE_URL,
                "sign_method": DEFAULT_PDD_SIGN_METHOD,
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
            "redirect_uri": row.redirect_uri,
            "api_base_url": row.api_base_url,
            "sign_method": row.sign_method,
            "is_enabled": bool(row.is_enabled),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        },
    }


@router.put("/pdd/app-config/current")
async def put_current_pdd_app_config(
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """
    保存当前拼多多系统配置。

    规则：
    - 若当前没有启用配置，则新建一条 enabled=true 记录
    - 若当前已有启用配置，则原地更新
    - 若 client_secret 为空字符串，则沿用原 secret（已有记录时）
    """
    require_platform_order_ingestion_write(db, current_user)

    client_id = str(payload.get("client_id") or "").strip()
    client_secret_raw = payload.get("client_secret")
    client_secret = str(client_secret_raw or "").strip()
    redirect_uri = str(payload.get("redirect_uri") or "").strip()
    api_base_url = str(payload.get("api_base_url") or DEFAULT_PDD_API_BASE_URL).strip()
    sign_method = str(payload.get("sign_method") or DEFAULT_PDD_SIGN_METHOD).strip().lower()

    try:
        current = await get_enabled_pdd_app_config(session)

        if current is None and not client_secret:
            raise ValueError("client_secret is required when creating pdd app config")

        secret_to_save: Optional[str]
        if client_secret:
            secret_to_save = client_secret
        else:
            secret_to_save = current.client_secret if current is not None else None

        row = await upsert_current_pdd_app_config(
            session,
            data=PddAppConfigUpsertInput(
                client_id=client_id,
                client_secret=secret_to_save,
                redirect_uri=redirect_uri,
                api_base_url=api_base_url,
                sign_method=sign_method,
                is_enabled=True,
            ),
        )
        await session.commit()
        await session.refresh(row)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"failed to save current pdd app config: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "id": row.id,
            "client_id": row.client_id,
            "client_secret_present": bool(str(row.client_secret or "").strip()),
            "client_secret_masked": _mask_secret(row.client_secret),
            "redirect_uri": row.redirect_uri,
            "api_base_url": row.api_base_url,
            "sign_method": row.sign_method,
            "is_enabled": bool(row.is_enabled),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        },
    }
