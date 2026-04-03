# app/oms/platforms/pdd/router_auth.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session

from .repository import require_enabled_pdd_app_config
from .service_auth import PddAuthService, PddAuthServiceError
from .settings import (
    build_pdd_open_config_from_model,
    build_pdd_redirect_uri_from_model,
)

router = APIRouter(tags=["oms-pdd-auth"])


@router.get("/pdd/oauth/start")
async def pdd_oauth_start(
    store_id: int = Query(..., ge=1),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        app_config = await require_enabled_pdd_app_config(session)
        service = PddAuthService(
            config=build_pdd_open_config_from_model(app_config),
            redirect_uri=build_pdd_redirect_uri_from_model(app_config),
        )
        result = service.build_authorize_url(store_id=store_id)
    except (ValueError, PddAuthServiceError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to build pdd authorize url: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "platform": "pdd",
            "store_id": result.store_id,
            "authorize_url": result.authorize_url,
            "state": result.state,
        },
    }


@router.get("/pdd/oauth/callback", name="oms_pdd_oauth_callback")
async def pdd_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        app_config = await require_enabled_pdd_app_config(session)
        service = PddAuthService(
            config=build_pdd_open_config_from_model(app_config),
            redirect_uri=build_pdd_redirect_uri_from_model(app_config),
        )
        result = await service.handle_callback(
            session=session,
            code=code,
            state=state,
        )
        await session.commit()
    except (ValueError, PddAuthServiceError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"failed to handle pdd oauth callback: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "platform": result.platform,
            "store_id": result.store_id,
            "owner_id": result.owner_id,
            "owner_name": result.owner_name,
            "access_token_present": bool(result.access_token),
            "refresh_token_present": bool(result.refresh_token),
            "expires_at": result.expires_at.isoformat(),
        },
    }
