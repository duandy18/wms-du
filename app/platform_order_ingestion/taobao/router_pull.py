# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/taobao/router_pull.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.oms.services.stores_helpers import check_perm

from .repository import require_enabled_taobao_app_config
from .service_pull import TaobaoPullService, TaobaoPullServiceError
from .settings import build_taobao_top_config_from_model


router = APIRouter(tags=["oms-taobao-pull"])


@router.post("/stores/{store_id}/taobao/test-pull")
async def test_store_taobao_pull(
    store_id: int = Path(..., ge=1),
    allow_real_request: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """
    淘宝 test-pull（第一版）。
    """
    check_perm(db, current_user, ["config.store.read"])

    try:
        app_config = await require_enabled_taobao_app_config(session)
        service = TaobaoPullService(
            session,
            config=build_taobao_top_config_from_model(app_config),
        )
        result = await service.check_pull_ready(
            store_id=store_id,
            allow_real_request=allow_real_request,
        )
    except (TaobaoPullServiceError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to run taobao test-pull: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "store_id": result.store_id,
            "platform": result.platform,
            "executed_real_pull": result.executed_real_pull,
            "pull_ready": result.pull_ready,
            "status": result.status,
            "status_reason": result.status_reason,
        },
    }
