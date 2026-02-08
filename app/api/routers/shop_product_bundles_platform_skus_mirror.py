# app/api/routers/shop_product_bundles_platform_skus_mirror.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.stores_helpers import check_perm
from app.db.deps import get_db


class PlatformSkuMirrorLine(BaseModel):
    item_name: str = Field(..., description="线索：商品名（只读）")
    spec: str | None = Field(None, description="线索：规格文案（只读，不解析）")
    quantity: float | None = Field(None, description="线索：数量（只读，不裁决）")


class PlatformSkuMirrorOut(BaseModel):
    platform: str
    shop_id: int
    platform_sku_id: str
    lines: list[PlatformSkuMirrorLine]


def register(router: APIRouter) -> None:
    r = APIRouter(prefix="/platform-skus", tags=["ops - shop-product-bundles"])

    @r.get("/mirror", response_model=PlatformSkuMirrorOut)
    def mirror(
        platform: str = Query(...),
        shop_id: int = Query(..., ge=1),
        platform_sku_id: str = Query(...),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> PlatformSkuMirrorOut:
        check_perm(db, current_user, ["config.store.write"])

        # ✅ 合同：mirror-first 读模型；只读线索，不做裁决/绑定。
        # 最小实现：若存在 mirror 行，则把 sku_name/spec 映射到 lines 的第一行。
        #
        # DB 事实：platform_sku_mirror 使用 store_id（stores.id）作为外键口径；
        # 对外合同仍沿用 shop_id（历史误名），其语义在此处等价为 store_id。
        row = (
            db.execute(
                text(
                    """
                    SELECT sku_name, spec
                      FROM platform_sku_mirror
                     WHERE platform = :platform
                       AND store_id = :store_id
                       AND platform_sku_id = :platform_sku_id
                     LIMIT 1
                    """
                ),
                {
                    "platform": str(platform),
                    "store_id": int(shop_id),
                    "platform_sku_id": str(platform_sku_id),
                },
            )
            .mappings()
            .first()
        )

        lines: list[PlatformSkuMirrorLine] = []
        if row:
            sku_name = row.get("sku_name") or ""
            spec = row.get("spec")
            if sku_name:
                lines.append(PlatformSkuMirrorLine(item_name=str(sku_name), spec=str(spec) if spec is not None else None))

        return PlatformSkuMirrorOut(platform=platform, shop_id=shop_id, platform_sku_id=platform_sku_id, lines=lines)

    router.include_router(r)
