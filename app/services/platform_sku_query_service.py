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

    - PSKU 来源（优先级 / 合并策略）：
      1) platform_sku_mirror（平台事实，包含 sku_name/spec 等线索）
      2) platform_sku_bindings distinct key（fallback/治理锚点：保证页面不空）

    ✅ 关键：不再是 “mirror 有数据就忽略 bindings”。
       列表永远是 mirror ∪ bindings(distinct key)，并按 mirror-first 输出。

    - 映射来源：current binding（effective_to IS NULL）
    - 单入口收敛：PSKU 只允许绑定到 FSKU（单品也必须通过 single-FSKU 表达）
    - 历史遗留的 item_id 绑定（legacy）在列表中按 unbound 处理，驱动迁移。

    ✅ 列表增强：
    - 对 bound 项带出 binding_id（用于 migrate）

    ✅ 合同升级：
    - 输出新增 store_id（stores.id）
    - 兼容保留 shop_id 字段名（语义等同 store_id）
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
        # ------------------------------------------------------------
        # 1) mirror 查询（平台事实）
        #    说明：分页语义采用 mirror-first：
        #    - 先消耗 mirror 序列（按 platform_sku_id 排序）
        #    - 若 page 还有空间，再用 bindings-only 补齐
        # ------------------------------------------------------------
        mirror_base = select(PlatformSkuMirror).where(PlatformSkuMirror.store_id == store_id)

        if q:
            like = f"%{q}%"
            mirror_base = mirror_base.where(
                PlatformSkuMirror.platform_sku_id.ilike(like)
                | PlatformSkuMirror.sku_name.ilike(like)
                | PlatformSkuMirror.spec.ilike(like)
            )

        mirror_total = int(self.db.scalar(select(func.count()).select_from(mirror_base.subquery())) or 0)

        # mirror 在合并序列中的 offset/limit
        mirror_offset = offset if offset < mirror_total else mirror_total
        mirror_limit = limit if offset < mirror_total else 0
        if offset < mirror_total:
            mirror_limit = min(limit, mirror_total - offset)

        mirror_rows = []
        if mirror_limit > 0:
            mirror_rows = self.db.scalars(
                mirror_base.order_by(PlatformSkuMirror.platform_sku_id)
                .limit(mirror_limit)
                .offset(mirror_offset)
            ).all()

        mirror_keys_in_page = {(m.platform, int(m.store_id), m.platform_sku_id) for m in mirror_rows}

        # ------------------------------------------------------------
        # 2) bindings-only keys（治理锚点）
        #    bindings-only = 在 bindings distinct key 里，但 mirror 不存在的 key
        #    注意：offset/limit 的后半段从 (offset - mirror_total) 开始
        # ------------------------------------------------------------
        bindings_only_base = (
            select(
                PlatformSkuBinding.platform,
                PlatformSkuBinding.store_id,
                PlatformSkuBinding.platform_sku_id,
            )
            .where(PlatformSkuBinding.store_id == store_id)
            .distinct()
        )

        if q:
            bindings_only_base = bindings_only_base.where(PlatformSkuBinding.platform_sku_id.ilike(f"%{q}%"))

        # 排除 mirror 已存在的 key（同 store_id 下相同三元组）
        # 用 NOT EXISTS 避免拉全量 key 到内存
        mirror_exists = (
            select(1)
            .select_from(PlatformSkuMirror)
            .where(
                PlatformSkuMirror.store_id == PlatformSkuBinding.store_id,
                PlatformSkuMirror.platform == PlatformSkuBinding.platform,
                PlatformSkuMirror.platform_sku_id == PlatformSkuBinding.platform_sku_id,
            )
            .limit(1)
        )
        bindings_only_base = bindings_only_base.where(~mirror_exists.exists())

        bindings_only_total = int(self.db.scalar(select(func.count()).select_from(bindings_only_base.subquery())) or 0)

        # bindings-only 在合并序列中的 offset/limit
        bindings_only_offset = 0
        bindings_only_limit = 0
        if offset >= mirror_total:
            bindings_only_offset = offset - mirror_total
            bindings_only_limit = limit
        else:
            bindings_only_offset = 0
            bindings_only_limit = max(0, limit - len(mirror_rows))

        bindings_only_rows = []
        if bindings_only_limit > 0 and (bindings_only_total > 0):
            bindings_only_rows = self.db.execute(
                bindings_only_base.order_by(PlatformSkuBinding.platform_sku_id)
                .limit(bindings_only_limit)
                .offset(bindings_only_offset)
            ).all()

        # ------------------------------------------------------------
        # 3) current bindings 映射（effective_to IS NULL）
        # ------------------------------------------------------------
        bindings: dict[tuple[str, int, str], PlatformSkuBinding] = {}
        if with_binding:
            b_rows = self.db.scalars(
                select(PlatformSkuBinding).where(
                    PlatformSkuBinding.store_id == store_id,
                    PlatformSkuBinding.effective_to.is_(None),
                )
            ).all()
            for b in b_rows:
                bindings[(b.platform, b.store_id, b.platform_sku_id)] = b

        def _binding_summary(b: PlatformSkuBinding | None) -> PlatformSkuBindingSummary:
            if b is None or b.fsku_id is None:
                return PlatformSkuBindingSummary(status="unbound")
            return PlatformSkuBindingSummary(
                status="bound",
                binding_id=b.id,
                target_type="fsku",
                fsku_id=b.fsku_id,
                effective_from=b.effective_from,
            )

        # ------------------------------------------------------------
        # 4) 组装 items：mirror-first + bindings-only
        # ------------------------------------------------------------
        items: list[PlatformSkuListItem] = []

        for m in mirror_rows:
            k = (m.platform, int(m.store_id), m.platform_sku_id)
            b = bindings.get(k)
            sid = int(m.store_id)
            items.append(
                PlatformSkuListItem(
                    platform=m.platform,
                    store_id=sid,
                    shop_id=sid,  # 兼容字段：语义等同 store_id
                    platform_sku_id=m.platform_sku_id,
                    sku_name=m.sku_name,
                    binding=_binding_summary(b),
                )
            )

        for platform, store_id2, platform_sku_id in bindings_only_rows:
            k = (platform, int(store_id2), platform_sku_id)

            if k in mirror_keys_in_page:
                continue

            b = bindings.get(k)
            sid2 = int(store_id2)
            items.append(
                PlatformSkuListItem(
                    platform=platform,
                    store_id=sid2,
                    shop_id=sid2,  # 兼容字段：语义等同 store_id
                    platform_sku_id=platform_sku_id,
                    sku_name=None,
                    binding=_binding_summary(b),
                )
            )

        total = mirror_total + bindings_only_total
        return PlatformSkuListOut(items=items, total=total, limit=limit, offset=offset)
