# app/oms/platforms/taobao/router_app_config.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.db.deps import get_db
from app.oms.routers import stores as stores_router

from .repository import (
    TaobaoAppConfigUpsertInput,
    get_enabled_taobao_app_config,
    upsert_current_taobao_app_config,
)
from .settings import (
    DEFAULT_TOP_API_BASE_URL,
    DEFAULT_TOP_SIGN_METHOD,
)

router = APIRouter(tags=["oms-taobao-app-config"])


def _mask_secret(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 6:
        return "*" * len(text)
    return f"{text[:3]}{'*' * (len(text) - 6)}{text[-3:]}"


@router.get("/taobao/app-config/current")
async def get_current_taobao_app_config(
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """
    读取当前启用中的淘宝系统配置。
    """
    stores_router._check_perm(db, current_user, ["config.store.read"])

    try:
        row = await get_enabled_taobao_app_config(session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to load current taobao app config: {exc}",
        ) from exc

    if row is None:
        return {
            "ok": True,
            "data": {
                "id": None,
                "app_key": "",
                "app_secret_present": False,
                "app_secret_masked": "",
                "callback_url": "",
                "api_base_url": DEFAULT_TOP_API_BASE_URL,
                "sign_method": DEFAULT_TOP_SIGN_METHOD,
                "is_enabled": False,
                "created_at": None,
                "updated_at": None,
            },
        }

    return {
        "ok": True,
        "data": {
            "id": row.id,
            "app_key": row.app_key,
            "app_secret_present": bool(str(row.app_secret or "").strip()),
            "app_secret_masked": _mask_secret(row.app_secret),
            "callback_url": row.callback_url,
            "api_base_url": row.api_base_url,
            "sign_method": row.sign_method,
            "is_enabled": bool(row.is_enabled),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        },
    }


@router.put("/taobao/app-config/current")
async def put_current_taobao_app_config(
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """
    保存当前淘宝系统配置。

    规则：
    - 若当前没有启用配置，则新建一条 enabled=true 记录
    - 若当前已有启用配置，则原地更新
    - 若 app_secret 为空字符串，则沿用原 secret（已有记录时）
    """
    stores_router._check_perm(db, current_user, ["config.store.read"])

    app_key = str(payload.get("app_key") or "").strip()
    app_secret_raw = payload.get("app_secret")
    app_secret = str(app_secret_raw or "").strip()
    callback_url = str(payload.get("callback_url") or "").strip()
    api_base_url = str(payload.get("api_base_url") or DEFAULT_TOP_API_BASE_URL).strip()
    sign_method = str(payload.get("sign_method") or DEFAULT_TOP_SIGN_METHOD).strip().lower()

    try:
        current = await get_enabled_taobao_app_config(session)

        if current is None and not app_secret:
            raise ValueError("app_secret is required when creating taobao app config")

        secret_to_save: Optional[str]
        if app_secret:
            secret_to_save = app_secret
        else:
            secret_to_save = current.app_secret if current is not None else None

        row = await upsert_current_taobao_app_config(
            session,
            data=TaobaoAppConfigUpsertInput(
                app_key=app_key,
                app_secret=secret_to_save,
                callback_url=callback_url,
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
            detail=f"failed to save current taobao app config: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "id": row.id,
            "app_key": row.app_key,
            "app_secret_present": bool(str(row.app_secret or "").strip()),
            "app_secret_masked": _mask_secret(row.app_secret),
            "callback_url": row.callback_url,
            "api_base_url": row.api_base_url,
            "sign_method": row.sign_method,
            "is_enabled": bool(row.is_enabled),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        },
    }
