# app/services/item_service.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import String, cast, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.item import Item

NOEXP_BATCH_CODE = "NOEXP"

SKU_SEQ_NAME = "items_sku_seq"
SKU_PREFIX = "AKT-"
SKU_PAD_WIDTH = 6


def _decorate_rules(obj: Item) -> Item:
    has_sl = bool(getattr(obj, "has_shelf_life", False))
    setattr(obj, "requires_batch", True if has_sl else False)
    setattr(obj, "requires_dates", True if has_sl else False)
    setattr(obj, "default_batch_code", None if has_sl else NOEXP_BATCH_CODE)
    return obj


class ItemService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def next_sku(self) -> str:
        n = self.db.execute(text(f"SELECT nextval('{SKU_SEQ_NAME}')")).scalar_one()
        num = str(int(n)).zfill(SKU_PAD_WIDTH)
        return f"{SKU_PREFIX}{num}"

    def create_item(
        self,
        *,
        name: str,
        spec: Optional[str] = None,
        uom: Optional[str] = None,
        barcode: Optional[str] = None,
        brand: Optional[str] = None,
        category: Optional[str] = None,
        enabled: bool = True,
        supplier_id: Optional[int] = None,
        has_shelf_life: Optional[bool] = None,
        shelf_life_value: Optional[int] = None,
        shelf_life_unit: Optional[str] = None,
        weight_kg: Optional[float] = None,
    ) -> Item:
        name = (name or "").strip()
        if not name:
            raise ValueError("name is required")

        spec_val = spec.strip() if isinstance(spec, str) else None
        unit_val = (uom or "PCS").strip().upper() or "PCS"

        brand_val = brand.strip() if isinstance(brand, str) and brand.strip() else None
        category_val = category.strip() if isinstance(category, str) and category.strip() else None

        sku_val = self.next_sku()

        obj = Item(
            sku=sku_val,
            name=name,
            unit=unit_val,
            spec=spec_val,
            enabled=bool(enabled),
            supplier_id=supplier_id,
            brand=brand_val,
            category=category_val,
            has_shelf_life=bool(has_shelf_life) if has_shelf_life is not None else False,
            shelf_life_value=shelf_life_value,
            shelf_life_unit=shelf_life_unit,
            weight_kg=weight_kg,
        )

        self.db.add(obj)
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raw = str(getattr(e, "orig", e)).lower()
            if "items_sku_key" in raw or ("unique" in raw and "sku" in raw):
                # 理论上不会发生（sequence 保证唯一），但保留防御
                raise ValueError("SKU duplicate") from e
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e

        self.db.refresh(obj)
        return _decorate_rules(obj)

    def create_item_by_id(
        self,
        *,
        id: int,
        sku: Optional[str] = None,
        name: Optional[str] = None,
        spec: Optional[str] = None,
        uom: Optional[str] = None,
        barcode: Optional[str] = None,
        brand: Optional[str] = None,
        category: Optional[str] = None,
        enabled: Optional[bool] = True,
        supplier_id: Optional[int] = None,
        has_shelf_life: Optional[bool] = None,
        shelf_life_value: Optional[int] = None,
        shelf_life_unit: Optional[str] = None,
        weight_kg: Optional[float] = None,
    ) -> Item:
        if not id or id <= 0:
            raise ValueError("id 必须为正整数")

        exists = self.db.get(Item, id)
        if exists is not None:
            return _decorate_rules(exists)

        sku_val = (sku or str(id)).strip()
        name_val = (name or f"ITEM-{id}").strip()
        spec_val = spec.strip() if isinstance(spec, str) else None
        unit_val = (uom or "PCS").strip().upper() or "PCS"
        enabled_val = True if enabled is None else bool(enabled)

        brand_val = brand.strip() if isinstance(brand, str) and brand.strip() else None
        category_val = category.strip() if isinstance(category, str) and category.strip() else None

        obj = Item(
            id=id,
            sku=sku_val,
            name=name_val,
            unit=unit_val,
            spec=spec_val,
            enabled=enabled_val,
            supplier_id=supplier_id,
            brand=brand_val,
            category=category_val,
            has_shelf_life=bool(has_shelf_life) if has_shelf_life is not None else False,
            shelf_life_value=shelf_life_value,
            shelf_life_unit=shelf_life_unit,
            weight_kg=weight_kg,
        )

        self.db.add(obj)
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raw = str(getattr(e, "orig", e)).lower()
            if "items_pkey" in raw:
                raise ValueError(f"Item id {id} already exists") from e
            if "items_sku_key" in raw:
                raise ValueError("SKU duplicate") from e
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e

        self.db.refresh(obj)
        return _decorate_rules(obj)

    # ✅ 支持 supplier_id / enabled / q / limit 过滤（主数据选择用）
    # - 不传参数：等价于旧行为（返回全量）
    def get_items(
        self,
        *,
        supplier_id: Optional[int] = None,
        enabled: Optional[bool] = None,
        q: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Item]:
        stmt = select(Item)

        if supplier_id is not None:
            stmt = stmt.where(Item.supplier_id == supplier_id)

        if enabled is not None:
            stmt = stmt.where(Item.enabled == enabled)

        q_raw = (q or "").strip()
        if q_raw:
            q_like = f"%{q_raw.lower()}%"

            conds = [
                func.lower(Item.sku).like(q_like),
                func.lower(Item.name).like(q_like),
                cast(Item.id, String).like(q_like),
            ]

            # barcode：只从真实表列读取，避免拿到 Python @property
            barcode_col = None
            try:
                barcode_col = Item.__table__.c.get("barcode")  # type: ignore[attr-defined]
            except Exception:
                barcode_col = None

            if barcode_col is not None:
                conds.append(func.lower(barcode_col).like(q_like))

            # 纯数字时，额外加 id 等值匹配（更精准）
            if q_raw.isdigit():
                try:
                    conds.append(Item.id == int(q_raw))
                except Exception:
                    pass

            stmt = stmt.where(or_(*conds))

        # limit：默认 50（当 q 存在时）；最大由路由层限制
        lim: Optional[int] = None
        if limit is not None:
            try:
                x = int(limit)
                if x > 0:
                    lim = x
            except Exception:
                lim = None
        elif q_raw:
            lim = 50

        stmt = stmt.order_by(Item.id.asc())
        if lim is not None:
            stmt = stmt.limit(lim)

        rows = self.db.execute(stmt).scalars().all()
        return [_decorate_rules(r) for r in rows]

    # 兼容旧接口：保留原方法名（供其它模块调用）
    def get_all_items(self) -> List[Item]:
        return self.get_items()

    def get_item_by_id(self, id: int) -> Optional[Item]:
        if not id or id <= 0:
            return None
        obj = self.db.get(Item, id)
        return _decorate_rules(obj) if obj else None

    def get_item_by_sku(self, sku: str) -> Optional[Item]:
        sku = (sku or "").strip()
        if not sku:
            return None
        obj = self.db.execute(select(Item).where(Item.sku == sku)).scalar_one_or_none()
        return _decorate_rules(obj) if obj else None

    def update_item(
        self,
        *,
        id: int,
        name: Optional[str] = None,
        spec: Optional[str] = None,
        uom: Optional[str] = None,
        enabled: Optional[bool] = None,
        supplier_id: Optional[int] = None,
        has_shelf_life: Optional[bool] = None,
        shelf_life_value: Optional[int] = None,
        shelf_life_unit: Optional[str] = None,
        weight_kg: Optional[float] = None,
        # ✅ 新增：brand/category（并支持显式置空）
        brand: Optional[str] = None,
        category: Optional[str] = None,
        brand_set: bool = False,
        category_set: bool = False,
    ) -> Item:
        obj = self.db.get(Item, id)
        if obj is None:
            raise ValueError("Item not found")

        changed = False

        if name is not None:
            new_name = name.strip()
            if not new_name:
                raise ValueError("name 不能为空")
            obj.name = new_name
            changed = True

        if spec is not None:
            obj.spec = spec.strip() if isinstance(spec, str) else None
            changed = True

        if uom is not None:
            unit_val = (uom or "PCS").strip().upper() or "PCS"
            obj.unit = unit_val
            changed = True

        if enabled is not None:
            obj.enabled = bool(enabled)
            changed = True

        if supplier_id is not None:
            obj.supplier_id = supplier_id
            changed = True

        if has_shelf_life is not None:
            obj.has_shelf_life = bool(has_shelf_life)
            changed = True

        if shelf_life_value is not None:
            obj.shelf_life_value = shelf_life_value
            changed = True

        if shelf_life_unit is not None:
            obj.shelf_life_unit = shelf_life_unit
            changed = True

        if weight_kg is not None:
            obj.weight_kg = weight_kg
            changed = True

        # ✅ brand/category：字段出现在 payload 就更新（哪怕是 None => 清空）
        if brand_set:
            obj.brand = brand.strip() if isinstance(brand, str) and brand.strip() else None
            changed = True

        if category_set:
            obj.category = category.strip() if isinstance(category, str) and category.strip() else None
            changed = True

        if not changed:
            return _decorate_rules(obj)

        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raise ValueError(f"DB integrity error: {getattr(e, 'orig', e)}") from e

        self.db.refresh(obj)
        return _decorate_rules(obj)
