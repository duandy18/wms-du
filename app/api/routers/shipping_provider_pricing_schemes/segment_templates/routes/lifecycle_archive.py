# app/api/routers/shipping_provider_pricing_schemes/segment_templates/routes/lifecycle_archive.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas.segment_template import SegmentTemplateDetailOut
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate
from app.models.shipping_provider_zone import ShippingProviderZone


def register_archive_routes(router: APIRouter) -> None:
    @router.post(
        "/segment-templates/{template_id}:archive",
        response_model=SegmentTemplateDetailOut,
    )
    def archive_template(
        template_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """
        ✅ 归档：只允许“已保存（published）且非当前生效”的模板归档
        - 归档后 status=archived
        - 归档后不可启用（activate 已经只允许 published）

        ✅ 免疫护栏（硬合同）：
        - 若仍有 Zone 引用该模板（zones.segment_template_id = template_id），禁止归档（409）
          避免制造“归档模板仍被引用”的脏状态。
        """
        check_perm(db, user, "config.store.write")

        tpl = db.get(ShippingProviderPricingSchemeSegmentTemplate, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Segment template not found")

        if tpl.is_active:
            raise HTTPException(status_code=409, detail="Active template cannot be archived")

        if tpl.status == "archived":
            raise HTTPException(status_code=409, detail="Template already archived")

        if tpl.status != "published":
            raise HTTPException(status_code=409, detail="Only published template can be archived")

        # ✅ 硬护栏：仍被 zone 引用则不允许归档
        refs = (
            db.query(ShippingProviderZone.id)
            .filter(ShippingProviderZone.segment_template_id == template_id)
            .order_by(ShippingProviderZone.id.asc())
            .limit(20)
            .all()
        )
        if refs:
            zone_ids = [int(x[0]) for x in refs if x and x[0] is not None]
            raise HTTPException(
                status_code=409,
                detail=(
                    "Cannot archive: template is still referenced by zones. "
                    f"Please unbind these zones first. zone_ids={zone_ids}"
                ),
            )

        tpl.status = "archived"
        tpl.is_active = False
        db.commit()
        db.refresh(tpl)
        return SegmentTemplateDetailOut(ok=True, data=tpl)

    @router.post(
        "/segment-templates/{template_id}:unarchive",
        response_model=SegmentTemplateDetailOut,
    )
    def unarchive_template(
        template_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """
        ✅ 取消归档：只允许“已归档（archived）”模板取消归档
        - 取消归档后 status=published
        - 取消归档后允许再次启用（activate 仍只允许 published）
        - 不引入通用 PATCH status 口子
        """
        check_perm(db, user, "config.store.write")

        tpl = db.get(ShippingProviderPricingSchemeSegmentTemplate, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Segment template not found")

        if tpl.status != "archived":
            raise HTTPException(status_code=409, detail="Only archived template can be unarchived")

        tpl.status = "published"
        tpl.is_active = False
        db.commit()
        db.refresh(tpl)
        return SegmentTemplateDetailOut(ok=True, data=tpl)
