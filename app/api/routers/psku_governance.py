# app/api/routers/psku_governance.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.stores_helpers import check_perm
from app.api.schemas.psku_governance import PskuGovernanceOut
from app.db.deps import get_db
from app.services.platform_sku_query_service import PlatformSkuQueryService

router = APIRouter(tags=["stores"])  # ✅ 复用 stores 的权限语义与分组（避免旁路）


@router.get("/psku-governance", response_model=PskuGovernanceOut)
def list_psku_governance(
    platform: str | None = Query(None, description="平台过滤（如 PDD/TB/DEMO），大小写不敏感"),
    store_id: int | None = Query(None, ge=1, description="内部店铺 store_id（stores.id）"),
    status: str | None = Query(None, description="治理状态过滤：BOUND / UNBOUND / LEGACY_ITEM_BOUND"),
    action: str | None = Query(None, description="行动过滤：OK / BIND_FIRST / MIGRATE_LEGACY"),
    q: str | None = Query(None, description="模糊搜索：platform_sku_id / sku_name / spec（mirror）/ fsku(code/name)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PskuGovernanceOut:
    check_perm(db, current_user, ["config.store.read"])

    svc = PlatformSkuQueryService(db)
    return svc.list_governance(
        platform=platform,
        store_id=store_id,
        status=status,
        action=action,
        limit=limit,
        offset=offset,
        q=q,
    )
