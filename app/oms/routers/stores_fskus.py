# app/oms/routers/stores_fskus.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.core.problem import make_problem
from app.oms.services.stores_bindings_helpers import check_store_perm
from app.oms.fsku.contracts.fsku import FskuListOut
from app.db.deps import get_db
from app.oms.fsku.services import fsku_service_read


def register(router: APIRouter) -> None:
    @router.get("/stores/{store_id}/fskus", response_model=FskuListOut)
    def list_store_fskus(
        store_id: int = Path(..., ge=1),
        query: str | None = Query(None, description="按 name/code 模糊搜索"),
        status_: str | None = Query(None, alias="status", description="draft/published/retired"),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> FskuListOut:
        # ✅ 权限与 stores 体系统一：config.store.read
        check_store_perm(db, current_user, ["config.store.read"])

        # ✅ store 必须存在（同步版本）
        exists = bool(
            db.execute(text("SELECT 1 FROM stores WHERE id = :sid LIMIT 1"), {"sid": int(store_id)}).scalar()
            or False
        )
        if not exists:
            raise HTTPException(
                status_code=404,
                detail=make_problem(
                    status_code=404,
                    error_code="not_found",
                    message="store not found",
                    context={"store_id": int(store_id)},
                ),
            )

        # ✅ store-scoped 口径：PROD 自动过滤测试 FSKU；TEST 不过滤
        return fsku_service_read.list_fskus(
            db,
            query=query,
            status=status_,
            store_id=int(store_id),
            limit=int(limit),
            offset=int(offset),
        )
