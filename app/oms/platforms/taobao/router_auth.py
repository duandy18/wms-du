# app/oms/platforms/taobao/router_auth.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session

from .repository import require_enabled_taobao_app_config
from .service_auth import (
    TaobaoAuthService,
    TaobaoAuthServiceError,
)
from .settings import (
    build_taobao_callback_url_from_model,
    build_taobao_top_config_from_model,
)

router = APIRouter(tags=["oms-taobao-auth"])


@router.get("/taobao/oauth/start")
async def taobao_oauth_start(
    store_id: int = Query(..., ge=1),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    生成淘宝授权链接。
    """
    try:
        app_config = await require_enabled_taobao_app_config(session)
        service = TaobaoAuthService(
            session,
            config=build_taobao_top_config_from_model(app_config),
            callback_url=build_taobao_callback_url_from_model(app_config),
        )
        result = service.build_authorize_url(store_id=store_id)
    except (TaobaoAuthServiceError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to build taobao authorize url: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "platform": "taobao",
            "store_id": store_id,
            "authorize_url": result.authorize_url,
            "state": result.state,
        },
    }


@router.get("/taobao/oauth/callback")
async def taobao_oauth_callback(
    code: str = Query(..., min_length=1),
    state: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    淘宝 OAuth callback。
    """
    try:
        app_config = await require_enabled_taobao_app_config(session)
        service = TaobaoAuthService(
            session,
            config=build_taobao_top_config_from_model(app_config),
            callback_url=build_taobao_callback_url_from_model(app_config),
        )
        result = await service.handle_callback(code=code, state=state)
    except (TaobaoAuthServiceError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to handle taobao oauth callback: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "platform": result.platform,
            "store_id": result.store_id,
            "access_token_present": bool(result.access_token),
            "refresh_token_present": bool(result.refresh_token),
            "expires_at": result.expires_at.isoformat(),
            "granted_identity_type": result.granted_identity_type,
            "granted_identity_value": result.granted_identity_value,
            "granted_identity_display": result.granted_identity_display,
        },
    }
