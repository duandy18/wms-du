# app/api/routers/shipping_provider_pricing_schemes_zones_helpers.py
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate
from app.models.shipping_provider_pricing_scheme_segment_template_item import ShippingProviderPricingSchemeSegmentTemplateItem
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket
from app.models.shipping_provider_zone_member import ShippingProviderZoneMember


def _norm_provinces(values: list[str] | None) -> list[str]:
    if not values:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def assert_segment_template_required(segment_template_id: int | None) -> None:
    # ✅ 硬合同：Zone 必须绑定模板（否则二维表不可解释）
    if segment_template_id is None:
        raise HTTPException(status_code=422, detail="segment_template_id is required (zone must bind a segment template)")


def load_template_or_422(db: Session, *, scheme_id: int, template_id: int) -> ShippingProviderPricingSchemeSegmentTemplate:
    t = db.get(ShippingProviderPricingSchemeSegmentTemplate, template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Segment template not found")

    if getattr(t, "scheme_id", None) != scheme_id:
        raise HTTPException(status_code=409, detail="Segment template does not belong to this scheme")

    # 这里不强卡 status/is_active：我们把“当前生效”定义在 Zone 命中上
    return t


def template_ranges(db: Session, template_id: int) -> set[tuple[float, float | None]]:
    """
    读取模板段结构（items）并转换成范围集合。
    - 用 float 作为集合 key，足够用于一致性校验（min/max 都是三位小数 kg）
    """
    items = (
        db.query(ShippingProviderPricingSchemeSegmentTemplateItem)
        .filter(ShippingProviderPricingSchemeSegmentTemplateItem.template_id == template_id)
        .order_by(
            ShippingProviderPricingSchemeSegmentTemplateItem.ord.asc(),
            ShippingProviderPricingSchemeSegmentTemplateItem.id.asc(),
        )
        .all()
    )

    ranges: set[tuple[float, float | None]] = set()
    for it in items:
        mn = float(getattr(it, "min_kg"))
        mx_raw = getattr(it, "max_kg", None)
        mx = float(mx_raw) if mx_raw is not None else None
        ranges.add((mn, mx))
    return ranges


def assert_zone_brackets_compatible_with_template(db: Session, *, zone_id: int, template_id: int) -> None:
    """
    护栏：若 zone 已存在 brackets，则不允许切换到“不兼容”的段结构模板。
    兼容定义：zone 的每条 bracket(min_kg,max_kg) 必须出现在模板 ranges 中。
    """
    bs = (
        db.query(ShippingProviderZoneBracket)
        .filter(ShippingProviderZoneBracket.zone_id == zone_id)
        .order_by(
            ShippingProviderZoneBracket.min_kg.asc(),
            ShippingProviderZoneBracket.max_kg.asc().nulls_last(),
            ShippingProviderZoneBracket.id.asc(),
        )
        .all()
    )
    if not bs:
        return

    allow = template_ranges(db, template_id)
    if not allow:
        raise HTTPException(status_code=409, detail="Selected segment template has no segments")

    bad: list[str] = []
    for b in bs:
        mn = float(b.min_kg)
        mx_raw = b.max_kg
        mx = float(mx_raw) if mx_raw is not None else None
        if (mn, mx) not in allow:
            bad.append(f"[{mn},{'' if mx is None else mx}]")

    if bad:
        raise HTTPException(
            status_code=409,
            detail=(
                "该区域已存在报价明细，切换重量段结构会导致范围不一致。"
                f"请先清理/迁移该 Zone 的 brackets 再切换。冲突范围示例：{', '.join(bad[:8])}"
            ),
        )


def assert_provinces_no_overlap(db: Session, *, scheme_id: int, provinces: list[str], exclude_zone_id: int | None = None) -> None:
    """
    ✅ 硬合同：同一 scheme 下 province 不得交叉归属多个 zone。
    - provinces: 本次要写入的最终省份集合（已清洗去重）
    - exclude_zone_id: 更新自身时排除自己
    """
    target = set(_norm_provinces(provinces))
    if not target:
        return

    q = (
        db.query(ShippingProviderZoneMember.zone_id, ShippingProviderZoneMember.value)
        .join(ShippingProviderZone, ShippingProviderZone.id == ShippingProviderZoneMember.zone_id)
        .filter(ShippingProviderZone.scheme_id == scheme_id)
        .filter(ShippingProviderZoneMember.level == "province")
    )
    if exclude_zone_id is not None:
        q = q.filter(ShippingProviderZoneMember.zone_id != exclude_zone_id)

    # province -> zone_ids
    hit: dict[str, set[int]] = {}
    for zid, prov in q.all():
        if prov is None:
            continue
        p = str(prov).strip()
        if not p:
            continue
        if p in target:
            hit.setdefault(p, set()).add(int(zid))

    if hit:
        overlapped = sorted(hit.keys())
        conflict_zone_ids = sorted({z for zs in hit.values() for z in zs})
        prov = "、".join(overlapped[:10])
        more = "" if len(overlapped) <= 10 else "…"
        raise HTTPException(
            status_code=409,
            detail=(
                f"区域划分冲突：同一收费标准（scheme_id={scheme_id}）下省份重复归属。"
                f"冲突省份：{prov}{more}；冲突区域ID：{conflict_zone_ids}"
            ),
        )
