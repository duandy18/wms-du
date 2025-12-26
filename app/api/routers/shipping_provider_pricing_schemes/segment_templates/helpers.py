# app/api/routers/shipping_provider_pricing_schemes/segment_templates/helpers.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.shipping_provider_pricing_scheme_segment import ShippingProviderPricingSchemeSegment
from app.models.shipping_provider_pricing_scheme_segment_template_item import (
    ShippingProviderPricingSchemeSegmentTemplateItem,
)


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def to_decimal(v: object, field: str) -> Decimal:
    try:
        return Decimal(str(v))
    except Exception:
        raise HTTPException(status_code=422, detail=f"{field} must be a number")


def validate_contiguous(rows: List[Tuple[int, Decimal, Optional[Decimal]]]) -> None:
    """
    rows: [(ord, min, max|None)]
    规则：
    - 至少 1 段
    - ord 必须从 0 连续
    - 第一段 min=0
    - 连续：next.min == prev.max（prev.max 不能为空）
    - ∞ 段（max None）必须最后
    - max>min（若非 None）
    """
    if not rows:
        raise HTTPException(status_code=422, detail="template items must have at least 1 segment")

    rows_sorted = sorted(rows, key=lambda x: x[0])
    for i, (ord_i, _, _) in enumerate(rows_sorted):
        if ord_i != i:
            raise HTTPException(status_code=422, detail="template items ord must be continuous from 0")

    if rows_sorted[0][1] != Decimal("0"):
        raise HTTPException(status_code=422, detail="template items[0].min_kg must be 0")

    for i in range(len(rows_sorted)):
        _, mn, mx = rows_sorted[i]
        if mn < 0:
            raise HTTPException(status_code=422, detail=f"template items[{i}].min_kg must be >= 0")
        if mx is not None and mx <= mn:
            raise HTTPException(status_code=422, detail=f"template items[{i}].max_kg must be > min_kg")

        if i == 0:
            continue
        _, _prev_mn, prev_mx = rows_sorted[i - 1]
        if prev_mx is None:
            raise HTTPException(status_code=422, detail="template has INF segment; it must be the last segment")
        if mn != prev_mx:
            raise HTTPException(
                status_code=422,
                detail="template items must be contiguous: min_kg must equal previous max_kg",
            )

    for i in range(len(rows_sorted) - 1):
        if rows_sorted[i][2] is None:
            raise HTTPException(status_code=422, detail="template has INF segment; it must be the last segment")


def template_to_scheme_segments_json(items: List[ShippingProviderPricingSchemeSegmentTemplateItem]) -> list:
    """
    把模板 items（数值）镜像回 scheme.segments_json（字符串口径）
    """
    out = []
    for it in sorted(items, key=lambda x: x.ord):
        mn = str(it.min_kg)
        if "." in mn:
            mn = mn.rstrip("0").rstrip(".")
        mx = ""
        if it.max_kg is not None:
            mx = str(it.max_kg)
            if "." in mx:
                mx = mx.rstrip("0").rstrip(".")
        out.append({"min": mn, "max": mx})
    return out


def sync_scheme_segments_table(db: Session, scheme_id: int, items: List[ShippingProviderPricingSchemeSegmentTemplateItem]) -> None:
    """
    启用模板后：把模板 items 镜像到现有 scheme_segments 表（你当前前端在用）
    - delete + insert
    - active 跟随模板 item.active
    """
    db.query(ShippingProviderPricingSchemeSegment).filter(
        ShippingProviderPricingSchemeSegment.scheme_id == scheme_id
    ).delete(synchronize_session=False)

    for it in sorted(items, key=lambda x: x.ord):
        db.add(
            ShippingProviderPricingSchemeSegment(
                scheme_id=scheme_id,
                ord=int(it.ord),
                min_kg=it.min_kg,
                max_kg=it.max_kg,
                active=bool(it.active),
            )
        )
