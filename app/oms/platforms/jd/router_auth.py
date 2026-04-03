# app/oms/platforms/jd/router_auth.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session

from .repository import require_enabled_jd_app_config
from .service_auth import JdAuthService, JdAuthServiceError
from .settings import (
    build_jd_callback_url_from_model,
    build_jd_jos_config_from_model,
)

router = APIRouter(tags=["oms-jd-auth"])


@router.get("/jd/oauth/start")
async def jd_oauth_start(
    store_id: int = Query(..., ge=1),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        app_config = await require_enabled_jd_app_config(session)
        service = JdAuthService(
            session,
            config=build_jd_jos_config_from_model(app_config),
            callback_url=build_jd_callback_url_from_model(app_config),
        )
        result = service.build_authorize_url(store_id=store_id)
    except (JdAuthServiceError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to build jd authorize url: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "platform": "jd",
            "store_id": result.store_id,
            "authorize_url": result.authorize_url,
            "state": result.state,
        },
    }


@router.get("/jd/oauth/callback")
async def jd_oauth_callback(
    code: str = Query(..., min_length=1),
    state: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        app_config = await require_enabled_jd_app_config(session)
        service = JdAuthService(
            session,
            config=build_jd_jos_config_from_model(app_config),
            callback_url=build_jd_callback_url_from_model(app_config),
        )
        result = await service.handle_callback(code=code, state=state)
    except (JdAuthServiceError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to handle jd oauth callback: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "platform": result.platform,
            "store_id": result.store_id,
            "uid": result.uid,
            "uid_display": result.uid_display,
            "access_token_present": bool(result.access_token),
            "refresh_token_present": bool(result.refresh_token),
            "expires_at": result.expires_at.isoformat(),
        },
    }
