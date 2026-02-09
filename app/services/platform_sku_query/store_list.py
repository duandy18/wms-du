# app/services/platform_sku_query/store_list.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas.platform_sku_list import (
    PlatformSkuBindingSummary,
    PlatformSkuListItem,
    PlatformSkuListOut,
)
from app.models.platform_sku_binding import PlatformSkuBinding
from app.models.platform_sku_mirror import PlatformSkuMirror
from app.services.platform_sku_query._common import (
    build_bindings_only_base,
    build_mirror_base,
    fetch_mirror_first_page,
)


def list_by_store(
    db: Session,
    *,
    store_id: int,
    with_binding: bool,
    limit: int,
    offset: int,
    q: str | None,
) -> PlatformSkuListOut:
    # 1) mirror / bindings-only base
    mirror_base = build_mirror_base(store_id=store_id, platform_upper=None, q=q).where(PlatformSkuMirror.store_id == store_id)
    bindings_only_base = build_bindings_only_base(store_id=store_id, platform_upper=None, q=q).where(PlatformSkuBinding.store_id == store_id)

    page = fetch_mirror_first_page(
        db,
        mirror_base=mirror_base,
        bindings_only_base=bindings_only_base,
        limit=limit,
        offset=offset,
        mirror_order_by=PlatformSkuMirror.platform_sku_id,
        bindings_only_order_by=PlatformSkuBinding.platform_sku_id,
    )

    # 2) current bindings map（store 视角只加载该 store 的 current）
    bindings: dict[tuple[str, int, str], PlatformSkuBinding] = {}
    if with_binding:
        b_rows = db.scalars(
            select(PlatformSkuBinding).where(
                PlatformSkuBinding.store_id == store_id,
                PlatformSkuBinding.effective_to.is_(None),
            )
        ).all()
        for b in b_rows:
            bindings[(b.platform, int(b.store_id), b.platform_sku_id)] = b

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

    # 3) assemble
    items: list[PlatformSkuListItem] = []

    mirror_keys_in_page = page.mirror_keys_in_page
    for m in page.mirror_rows:
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

    for platform2, store_id2, platform_sku_id2 in page.bindings_only_rows:
        k2 = (platform2, int(store_id2), platform_sku_id2)
        if k2 in mirror_keys_in_page:
            continue
        b = bindings.get(k2)
        sid2 = int(store_id2)
        items.append(
            PlatformSkuListItem(
                platform=platform2,
                store_id=sid2,
                shop_id=sid2,  # 兼容字段：语义等同 store_id
                platform_sku_id=platform_sku_id2,
                sku_name=None,
                binding=_binding_summary(b),
            )
        )

    total = page.mirror_total + page.bindings_only_total
    return PlatformSkuListOut(items=items, total=total, limit=limit, offset=offset)
