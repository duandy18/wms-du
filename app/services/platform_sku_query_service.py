# app/services/platform_sku_query_service.py
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas.platform_sku_list import (
    PlatformSkuBindingSummary,
    PlatformSkuListItem,
    PlatformSkuListOut,
)
from app.models.platform_sku_binding import PlatformSkuBinding
from app.models.platform_sku_mirror import PlatformSkuMirror


class PlatformSkuQueryService:
    """
    PSKU 聚合只读查询（Store 视角）：

    - PSKU 来源（优先级）：
      1) platform_sku_mirror（平台事实，包含 sku_name/spec 等线索）
      2) platform_sku_bindings distinct key（fallback，保证页面不空）

    - 映射来源：current binding（effective_to IS NULL）

    ✅ 收敛：PSKU 只允许绑定到 FSKU（单品也必须通过 single-FSKU 表达）
    - 历史遗留的 item_id 绑定（legacy）在列表中按 unbound 处理，驱动迁移。
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
        # -------------------------
        # 1) mirror 优先（平台事实）
        # -------------------------
        mirror_base = select(PlatformSkuMirror).where(PlatformSkuMirror.shop_id == store_id)

        if q:
            like = f"%{q}%"
            mirror_base = mirror_base.where(
                PlatformSkuMirror.platform_sku_id.ilike(like)
                | PlatformSkuMirror.sku_name.ilike(like)
                | PlatformSkuMirror.spec.ilike(like)
            )

        mirror_total = int(self.db.scalar(select(func.count()).select_from(mirror_base.subquery())) or 0)
        mirror_rows = self.db.scalars(
            mirror_base.order_by(PlatformSkuMirror.platform_sku_id).limit(limit).offset(offset)
        ).all()

        # -------------------------
        # 2) mirror 为空 -> fallback
        # -------------------------
        if mirror_total == 0:
            base = (
                select(
                    PlatformSkuBinding.platform,
                    PlatformSkuBinding.shop_id,
                    PlatformSkuBinding.platform_sku_id,
                )
                .where(PlatformSkuBinding.shop_id == store_id)
                .distinct()
            )

            if q:
                base = base.where(PlatformSkuBinding.platform_sku_id.ilike(f"%{q}%"))

            total = int(self.db.scalar(select(func.count()).select_from(base.subquery())) or 0)

            rows = self.db.execute(
                base.order_by(PlatformSkuBinding.platform_sku_id).limit(limit).offset(offset)
            ).all()

            bindings: dict[tuple[str, int, str], PlatformSkuBinding] = {}
            if with_binding:
                b_rows = self.db.scalars(
                    select(PlatformSkuBinding).where(
                        PlatformSkuBinding.shop_id == store_id,
                        PlatformSkuBinding.effective_to.is_(None),
                    )
                ).all()
                for b in b_rows:
                    bindings[(b.platform, b.shop_id, b.platform_sku_id)] = b

            items: list[PlatformSkuListItem] = []
            for platform, shop_id, platform_sku_id in rows:
                b = bindings.get((platform, shop_id, platform_sku_id))

                # ✅ 只承认 fsku_id；item_id legacy 当作 unbound
                if b is None or b.fsku_id is None:
                    binding = PlatformSkuBindingSummary(status="unbound")
                else:
                    binding = PlatformSkuBindingSummary(
                        status="bound",
                        target_type="fsku",
                        fsku_id=b.fsku_id,
                        effective_from=b.effective_from,
                    )

                items.append(
                    PlatformSkuListItem(
                        platform=platform,
                        shop_id=shop_id,
                        platform_sku_id=platform_sku_id,
                        sku_name=None,
                        binding=binding,
                    )
                )

            return PlatformSkuListOut(items=items, total=total, limit=limit, offset=offset)

        # -------------------------
        # 3) mirror 有数据：补 current binding
        # -------------------------
        bindings: dict[tuple[str, int, str], PlatformSkuBinding] = {}
        if with_binding:
            b_rows = self.db.scalars(
                select(PlatformSkuBinding).where(
                    PlatformSkuBinding.shop_id == store_id,
                    PlatformSkuBinding.effective_to.is_(None),
                )
            ).all()
            for b in b_rows:
                bindings[(b.platform, b.shop_id, b.platform_sku_id)] = b

        items: list[PlatformSkuListItem] = []
        for m in mirror_rows:
            b = bindings.get((m.platform, m.shop_id, m.platform_sku_id))

            # ✅ 只承认 fsku_id；item_id legacy 当作 unbound
            if b is None or b.fsku_id is None:
                binding = PlatformSkuBindingSummary(status="unbound")
            else:
                binding = PlatformSkuBindingSummary(
                    status="bound",
                    target_type="fsku",
                    fsku_id=b.fsku_id,
                    effective_from=b.effective_from,
                )

            items.append(
                PlatformSkuListItem(
                    platform=m.platform,
                    shop_id=int(m.shop_id),
                    platform_sku_id=m.platform_sku_id,
                    sku_name=m.sku_name,
                    binding=binding,
                )
            )

        return PlatformSkuListOut(items=items, total=mirror_total, limit=limit, offset=offset)
