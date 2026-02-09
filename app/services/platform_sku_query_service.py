# app/services/platform_sku_query_service.py
from __future__ import annotations

from sqlalchemy.orm import Session

from app.api.schemas.platform_sku_list import PlatformSkuListOut
from app.api.schemas.psku_governance import PskuGovernanceOut
from app.services.platform_sku_query import governance_list, store_list


class PlatformSkuQueryService:
    """
    PSKU 查询门面（保持旧 import 路径稳定）。

    - store 视角：list_by_store（mirror ∪ bindings key，mirror-first）
    - 全局治理：list_governance（同一合并语义的系统级视图）
    """

    def __init__(self, db: Session):
        self.db = db

    def list_by_store(
        self,
        *,
        store_id: int,
        with_binding: bool,
        limit: int,
        offset: int,
        q: str | None,
    ) -> PlatformSkuListOut:
        return store_list.list_by_store(
            self.db,
            store_id=store_id,
            with_binding=with_binding,
            limit=limit,
            offset=offset,
            q=q,
        )

    def list_governance(
        self,
        *,
        platform: str | None,
        store_id: int | None,
        status: str | None,
        action: str | None,
        limit: int,
        offset: int,
        q: str | None,
    ) -> PskuGovernanceOut:
        return governance_list.list_governance(
            self.db,
            platform=platform,
            store_id=store_id,
            status=status,
            action=action,
            limit=limit,
            offset=offset,
            q=q,
        )
