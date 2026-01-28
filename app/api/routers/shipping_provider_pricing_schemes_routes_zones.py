# app/api/routers/shipping_provider_pricing_schemes_routes_zones.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_zone_out
from app.api.routers.shipping_provider_pricing_schemes_schemas import (
    ZoneCreateAtomicIn,
    ZoneCreateIn,
    ZoneOut,
    ZoneUpdateIn,
    ZoneProvinceMembersReplaceIn,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import (
    check_perm,
    clean_list_str,
    norm_nonempty,
)
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate
from app.models.shipping_provider_pricing_scheme_segment_template_item import ShippingProviderPricingSchemeSegmentTemplateItem
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket
from app.models.shipping_provider_zone_member import ShippingProviderZoneMember


def _load_template_or_422(db: Session, *, scheme_id: int, template_id: int) -> ShippingProviderPricingSchemeSegmentTemplate:
    t = db.get(ShippingProviderPricingSchemeSegmentTemplate, template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Segment template not found")

    if getattr(t, "scheme_id", None) != scheme_id:
        raise HTTPException(status_code=409, detail="Segment template does not belong to this scheme")

    # 可选：如果你们模板有 status/is_active 的“发布/生效”概念，可以在这里再加硬校验
    # 目前先不强卡状态，只做“同 scheme”事实约束（最小可用且不误杀）
    return t


def _template_ranges(db: Session, template_id: int) -> set[tuple[float, float | None]]:
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


def _assert_zone_brackets_compatible_with_template(db: Session, *, zone_id: int, template_id: int) -> None:
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

    allow = _template_ranges(db, template_id)
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


def register_zones_routes(router: APIRouter) -> None:
    @router.post(
        "/pricing-schemes/{scheme_id}/zones",
        response_model=ZoneOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_zone(
        scheme_id: int = Path(..., ge=1),
        payload: ZoneCreateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        # ✅ Zone 绑定段结构模板（可选）
        seg_tpl_id = getattr(payload, "segment_template_id", None)
        if seg_tpl_id is not None:
            _load_template_or_422(db, scheme_id=scheme_id, template_id=int(seg_tpl_id))

        z = ShippingProviderZone(
            scheme_id=scheme_id,
            name=norm_nonempty(payload.name, "name"),
            active=bool(payload.active),
            segment_template_id=int(seg_tpl_id) if seg_tpl_id is not None else None,
        )
        db.add(z)
        db.commit()
        db.refresh(z)
        return to_zone_out(z, [], [])

    @router.post(
        "/pricing-schemes/{scheme_id}/zones-atomic",
        response_model=ZoneOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_zone_atomic(
        scheme_id: int = Path(..., ge=1),
        payload: ZoneCreateAtomicIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        provinces = clean_list_str(payload.provinces)
        if not provinces:
            raise HTTPException(status_code=422, detail="provinces is required (>=1)")

        # ✅ Zone 绑定段结构模板（可选）
        seg_tpl_id = getattr(payload, "segment_template_id", None)
        if seg_tpl_id is not None:
            _load_template_or_422(db, scheme_id=scheme_id, template_id=int(seg_tpl_id))

        z = ShippingProviderZone(
            scheme_id=scheme_id,
            name=norm_nonempty(payload.name, "name"),
            active=bool(payload.active),
            segment_template_id=int(seg_tpl_id) if seg_tpl_id is not None else None,
        )

        try:
            db.add(z)
            db.flush()

            members = [ShippingProviderZoneMember(zone_id=z.id, level="province", value=p) for p in provinces]
            db.add_all(members)

            db.commit()
            db.refresh(z)
        except IntegrityError as e:
            db.rollback()
            msg = (str(e.orig) if getattr(e, "orig", None) is not None else str(e)).lower()

            if "uq_sp_zones_scheme_name" in msg:
                raise HTTPException(status_code=409, detail="Zone name already exists in this scheme")
            if "uq_sp_zone_members_zone_level_value" in msg:
                raise HTTPException(status_code=409, detail="Zone members conflict (duplicate level/value)")
            raise HTTPException(status_code=409, detail="Conflict while creating zone and members")

        members_db = (
            db.query(ShippingProviderZoneMember)
            .filter(ShippingProviderZoneMember.zone_id == z.id)
            .order_by(
                ShippingProviderZoneMember.level.asc(),
                ShippingProviderZoneMember.value.asc(),
                ShippingProviderZoneMember.id.asc(),
            )
            .all()
        )
        return to_zone_out(z, members_db, [])

    @router.patch(
        "/zones/{zone_id}",
        response_model=ZoneOut,
    )
    def update_zone(
        zone_id: int = Path(..., ge=1),
        payload: ZoneUpdateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        z = db.get(ShippingProviderZone, zone_id)
        if not z:
            raise HTTPException(status_code=404, detail="Zone not found")

        data = payload.dict(exclude_unset=True)

        if "name" in data:
            z.name = norm_nonempty(data.get("name"), "name")
        if "active" in data:
            z.active = bool(data["active"])

        # ✅ Zone 切换段结构模板（可选）
        if "segment_template_id" in data:
            next_tpl_id = data.get("segment_template_id", None)
            if next_tpl_id is None:
                # 解绑：回到“沿用 scheme 默认段结构”
                z.segment_template_id = None
            else:
                # 1) 模板必须属于同 scheme
                _load_template_or_422(db, scheme_id=z.scheme_id, template_id=int(next_tpl_id))
                # 2) 若该 zone 已有 brackets，必须兼容
                _assert_zone_brackets_compatible_with_template(db, zone_id=zone_id, template_id=int(next_tpl_id))
                z.segment_template_id = int(next_tpl_id)

        db.commit()
        db.refresh(z)

        members = (
            db.query(ShippingProviderZoneMember)
            .filter(ShippingProviderZoneMember.zone_id == zone_id)
            .order_by(
                ShippingProviderZoneMember.level.asc(),
                ShippingProviderZoneMember.value.asc(),
                ShippingProviderZoneMember.id.asc(),
            )
            .all()
        )
        brackets = (
            db.query(ShippingProviderZoneBracket)
            .filter(ShippingProviderZoneBracket.zone_id == zone_id)
            .order_by(
                ShippingProviderZoneBracket.min_kg.asc(),
                ShippingProviderZoneBracket.max_kg.asc().nulls_last(),
                ShippingProviderZoneBracket.id.asc(),
            )
            .all()
        )
        return to_zone_out(z, members, brackets)

    # ✅ 新增：原子替换某个 Zone 的 province members（用于“编辑省份”）
    @router.put(
        "/zones/{zone_id}/province-members",
        response_model=ZoneOut,
    )
    def replace_zone_province_members(
        zone_id: int = Path(..., ge=1),
        payload: ZoneProvinceMembersReplaceIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        z = db.get(ShippingProviderZone, zone_id)
        if not z:
            raise HTTPException(status_code=404, detail="Zone not found")

        provinces = clean_list_str(payload.provinces)
        if not provinces:
            raise HTTPException(status_code=422, detail="provinces is required (>=1)")

        try:
            # 只替换 province 级别 members，其他 level 不动
            db.query(ShippingProviderZoneMember).filter(
                ShippingProviderZoneMember.zone_id == zone_id,
                ShippingProviderZoneMember.level == "province",
            ).delete(synchronize_session=False)

            db.add_all([ShippingProviderZoneMember(zone_id=zone_id, level="province", value=p) for p in provinces])

            db.commit()
            db.refresh(z)
        except IntegrityError as e:
            db.rollback()
            msg = (str(e.orig) if getattr(e, "orig", None) is not None else str(e)).lower()
            if "uq_sp_zone_members_zone_level_value" in msg:
                raise HTTPException(status_code=409, detail="Zone members conflict (duplicate level/value)")
            raise HTTPException(status_code=409, detail="Conflict while replacing zone province members")

        members = (
            db.query(ShippingProviderZoneMember)
            .filter(ShippingProviderZoneMember.zone_id == zone_id)
            .order_by(
                ShippingProviderZoneMember.level.asc(),
                ShippingProviderZoneMember.value.asc(),
                ShippingProviderZoneMember.id.asc(),
            )
            .all()
        )
        brackets = (
            db.query(ShippingProviderZoneBracket)
            .filter(ShippingProviderZoneBracket.zone_id == zone_id)
            .order_by(
                ShippingProviderZoneBracket.min_kg.asc(),
                ShippingProviderZoneBracket.max_kg.asc().nulls_last(),
                ShippingProviderZoneBracket.id.asc(),
            )
            .all()
        )
        return to_zone_out(z, members, brackets)

    @router.delete(
        "/zones/{zone_id}",
        status_code=status.HTTP_200_OK,
    )
    def delete_zone(
        zone_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        z = db.get(ShippingProviderZone, zone_id)
        if not z:
            raise HTTPException(status_code=404, detail="Zone not found")

        db.delete(z)
        db.commit()
        return {"ok": True}
