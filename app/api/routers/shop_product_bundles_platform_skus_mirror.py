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

    # ✅ 新合同：内部治理一律用 store_id（stores.id）
    store_id: int

    # ⚠️ 兼容字段：历史合同名 shop_id（语义等同于 store_id）
    shop_id: int

    platform_sku_id: str
    lines: list[PlatformSkuMirrorLine]


def _pick_store_id(*, store_id: int | None, shop_id: int | None) -> int:
    """
    ✅ 合同升级（兼容期）：
    - 新参数：store_id（内部 stores.id）
    - 旧参数：shop_id（兼容旧字段名，语义等同 stores.id）
    """
    if store_id is not None:
        return int(store_id)
    if shop_id is not None:
        return int(shop_id)
    raise ValueError("store_id is required")


def register(router: APIRouter) -> None:
    r = APIRouter(prefix="/platform-skus", tags=["ops - shop-product-bundles"])

    @r.get("/mirror", response_model=PlatformSkuMirrorOut)
    def mirror(
        platform: str = Query(...),
        store_id: int | None = Query(None, ge=1, description="内部店铺ID（stores.id）"),
        shop_id: int | None = Query(None, ge=1, description="兼容旧参数：语义等同 stores.id"),
        platform_sku_id: str = Query(...),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> PlatformSkuMirrorOut:
        check_perm(db, current_user, ["config.store.write"])

        sid = _pick_store_id(store_id=store_id, shop_id=shop_id)

        # ✅ 合同：mirror-first 读模型；只读线索，不做裁决/绑定。
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
                    "store_id": int(sid),
                    "platform_sku_id": str(platform_sku_id),
                },
            )
            .mappings()
            .first()
        )

        lines: list[PlatformSkuMirrorLine] = []
        if row:
            sku_name = row.get("sku_name") or ""
            spec2 = row.get("spec")
            if sku_name:
                lines.append(PlatformSkuMirrorLine(item_name=str(sku_name), spec=str(spec2) if spec2 is not None else None))

        return PlatformSkuMirrorOut(
            platform=platform,
            store_id=int(sid),
            shop_id=int(sid),
            platform_sku_id=platform_sku_id,
            lines=lines,
        )

    router.include_router(r)
