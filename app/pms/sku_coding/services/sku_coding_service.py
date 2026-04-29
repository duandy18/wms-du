# app/pms/sku_coding/services/sku_coding_service.py
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.pms.items.models.item import Item
from app.pms.items.models.item_sku_code import ItemSkuCode
from app.pms.sku_coding.models.sku_coding import (
    SkuBusinessCategory,
    SkuCodeBrand,
    SkuCodeTemplate,
    SkuCodeTerm,
    SkuCodeTermGroup,
)


def _norm_code(v: str) -> str:
    s = (v or "").strip().upper()
    s = re.sub(r"\s+", "", s)
    return s


def normalize_spec_text(v: str) -> str:
    raw = (v or "").strip()
    if not raw:
        raise ValueError("spec_text 不能为空")

    s = raw.replace("×", "x").replace("*", "x").replace("Ｘ", "x").replace("x", "X")
    s = re.sub(r"\s+", "", s)

    m = re.fullmatch(r"(\d+(?:\.\d+)?)(kg|KG|千克)(?:X(\d+))?", s)
    if m:
        try:
            grams = Decimal(m.group(1)) * Decimal("1000")
        except InvalidOperation as e:
            raise ValueError("规格格式不合法") from e
        if grams != grams.to_integral_value():
            raise ValueError("kg 规格换算后必须是整数克")
        base = f"{int(grams)}G"
        return f"{base}X{int(m.group(3))}" if m.group(3) else base

    m = re.fullmatch(r"(\d+(?:\.\d+)?)(g|G|克)(?:X(\d+))?", s)
    if m:
        try:
            grams = Decimal(m.group(1))
        except InvalidOperation as e:
            raise ValueError("规格格式不合法") from e
        if grams != grams.to_integral_value():
            raise ValueError("g 规格必须是整数")
        base = f"{int(grams)}G"
        return f"{base}X{int(m.group(3))}" if m.group(3) else base

    m = re.fullmatch(r"(\d+(?:\.\d+)?)(l|L|升)(?:X(\d+))?", s)
    if m:
        num = Decimal(m.group(1))
        base = f"{int(num) if num == num.to_integral_value() else str(num).rstrip('0').rstrip('.')}L"
        return f"{base}X{int(m.group(3))}" if m.group(3) else base

    upper = _norm_code(s)
    if not re.fullmatch(r"[A-Z0-9]+(?:X[A-Z0-9]+)?", upper):
        raise ValueError("规格格式不支持，请输入如 500g、1.5kg、40g×6、2L")
    return upper


@dataclass(frozen=True)
class GeneratedSegment:
    segment_key: str
    name_cn: str
    code: str


class SkuCodingService:
    def __init__(self, db: Session):
        self.db = db

    def _get_brand(self, brand_id: int) -> SkuCodeBrand:
        obj = self.db.get(SkuCodeBrand, int(brand_id))
        if obj is None or not bool(obj.is_active):
            raise ValueError("品牌不存在或已停用")
        return obj

    def _get_category(self, category_id: int, *, product_kind: str) -> SkuBusinessCategory:
        obj = self.db.get(SkuBusinessCategory, int(category_id))
        if obj is None or not bool(obj.is_active):
            raise ValueError("内部分类不存在或已停用")
        if obj.product_kind != product_kind:
            raise ValueError("内部分类商品类型不匹配")
        if not bool(obj.is_leaf):
            raise ValueError("必须选择第三级叶子分类")
        return obj

    def _get_active_template(self, *, product_kind: str) -> SkuCodeTemplate:
        obj = (
            self.db.execute(
                select(SkuCodeTemplate)
                .options(selectinload(SkuCodeTemplate.segments))
                .where(SkuCodeTemplate.product_kind == product_kind, SkuCodeTemplate.is_active.is_(True))
                .order_by(SkuCodeTemplate.id.asc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if obj is None:
            raise ValueError(f"缺少 SKU 编码模板：{product_kind}")
        return obj

    def _load_terms_by_group(self, *, group_code: str, ids: list[int]) -> list[SkuCodeTerm]:
        normalized_ids = sorted({int(x) for x in ids if x is not None})
        if not normalized_ids:
            return []

        rows = (
            self.db.execute(
                select(SkuCodeTerm)
                .join(SkuCodeTermGroup, SkuCodeTermGroup.id == SkuCodeTerm.group_id)
                .where(
                    SkuCodeTerm.id.in_(normalized_ids),
                    SkuCodeTerm.is_active.is_(True),
                    SkuCodeTermGroup.group_code == group_code,
                )
                .order_by(SkuCodeTerm.sort_order.asc(), SkuCodeTerm.code.asc(), SkuCodeTerm.id.asc())
            )
            .scalars()
            .all()
        )
        if len(rows) != len(normalized_ids):
            raise ValueError(f"字典项不存在、已停用或分组不匹配：{group_code}")
        return list(rows)

    def generate(
        self,
        *,
        product_kind: str,
        brand_id: int,
        category_id: int,
        term_ids: dict[str, list[int]],
        text_segments: dict[str, str],
        spec_text: str,
    ) -> dict:
        kind = _norm_code(product_kind)
        brand = self._get_brand(brand_id)
        category = self._get_category(category_id, product_kind=kind)
        template = self._get_active_template(product_kind=kind)

        parts: list[str] = [str(template.prefix)]
        segments: list[GeneratedSegment] = []

        for segment in sorted(template.segments, key=lambda x: (int(x.sort_order), int(x.id))):
            key = str(segment.segment_key)
            source = str(segment.source_type)

            if source == "BRAND":
                parts.append(_norm_code(brand.code))
                segments.append(GeneratedSegment(key, brand.name_cn, _norm_code(brand.code)))
                continue

            if source == "CATEGORY":
                parts.append(_norm_code(category.category_code))
                segments.append(GeneratedSegment(key, category.category_name, _norm_code(category.category_code)))
                continue

            if source == "SPEC":
                code = normalize_spec_text(spec_text)
                parts.append(code)
                segments.append(GeneratedSegment(key, spec_text, code))
                continue

            if source == "TEXT":
                raw = (text_segments or {}).get(key)
                if raw is None or not str(raw).strip():
                    if bool(segment.is_required):
                        raise ValueError(f"缺少必填文本段：{key}")
                    continue
                code = _norm_code(str(raw))
                parts.append(code)
                segments.append(GeneratedSegment(key, str(raw).strip(), code))
                continue

            if source == "TERM":
                group = segment.term_group
                if group is None:
                    raise ValueError(f"模板段缺少 term_group：{key}")
                ids = (term_ids or {}).get(str(group.group_code), [])
                terms = self._load_terms_by_group(group_code=str(group.group_code), ids=ids)
                if not terms:
                    if bool(segment.is_required):
                        raise ValueError(f"缺少必填字典段：{group.group_code}")
                    continue
                if not bool(segment.is_multi_select) and len(terms) > 1:
                    raise ValueError(f"字典段不允许多选：{group.group_code}")
                for term in terms:
                    parts.append(_norm_code(term.code))
                    segments.append(GeneratedSegment(key, term.name_cn, _norm_code(term.code)))
                continue

            raise ValueError(f"不支持的模板段来源：{source}")

        sku = str(template.separator).join([p for p in parts if p])

        matched_code_item_ids = select(ItemSkuCode.item_id).where(ItemSkuCode.code == sku)
        exists = self.db.execute(select(ItemSkuCode.id).where(ItemSkuCode.code == sku).limit(1)).first() is not None
        similar_rows = (
            self.db.execute(
                select(Item)
                .where(
                    (Item.brand == brand.name_cn)
                    | (Item.category == category.category_name)
                    | (Item.sku == sku)
                    | (Item.id.in_(matched_code_item_ids))
                )
                .order_by(Item.id.desc())
                .limit(10)
            )
            .scalars()
            .all()
        )

        return {
            "sku": sku,
            "segments": [
                {"segment_key": s.segment_key, "name_cn": s.name_cn, "code": s.code}
                for s in segments
            ],
            "exists": exists,
            "similar_items": [
                {
                    "id": int(item.id),
                    "sku": str(item.sku),
                    "name": str(item.name),
                    "spec": item.spec,
                    "brand": item.brand,
                    "category": item.category,
                }
                for item in similar_rows
            ],
        }
