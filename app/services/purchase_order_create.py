# app/services/purchase_order_create.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine


async def _load_items_map(session: AsyncSession, item_ids: List[int]) -> Dict[int, Item]:
    if not item_ids:
        return {}
    rows = (
        (await session.execute(select(Item).where(Item.id.in_(item_ids))))
        .scalars()
        .all()
    )
    return {int(it.id): it for it in rows}


def _require_supplier_for_po(supplier_id: Optional[int]) -> int:
    if supplier_id is None:
        raise ValueError("supplier_id 不能为空：采购单必须绑定供应商")
    sid = int(supplier_id)
    if sid <= 0:
        raise ValueError("supplier_id 非法：采购单必须绑定供应商")
    return sid


async def create_po_v2(
    session: AsyncSession,
    *,
    supplier: str,
    warehouse_id: int,
    supplier_id: Optional[int] = None,
    supplier_name: Optional[str] = None,
    purchaser: str,
    purchase_time: datetime,
    remark: Optional[str] = None,
    lines: List[Dict[str, Any]],
) -> PurchaseOrder:
    """
    创建“头 + 多行”的采购单。
    """
    if not lines:
        raise ValueError("create_po_v2 需要至少一行行项目（lines 不可为空）")

    if not purchaser or not purchaser.strip():
        raise ValueError("采购人 purchaser 不能为空")

    if not isinstance(purchase_time, datetime):
        raise ValueError("purchase_time 必须为 datetime 类型")

    # ✅ 采购事实硬闸：采购单必须绑定供应商（否则无法做到“供应商->商品”的事实约束）
    po_supplier_id = _require_supplier_for_po(supplier_id)

    # 先收集 item_ids，用于批量查 Item（避免 N+1）
    raw_item_ids: List[int] = []
    for idx, raw in enumerate(lines, start=1):
        item_id = raw.get("item_id")
        qty_ordered = raw.get("qty_ordered")
        if item_id is None or qty_ordered is None:
            raise ValueError("每一行必须包含 item_id 与 qty_ordered")
        try:
            raw_item_ids.append(int(item_id))
        except Exception as e:
            raise ValueError(f"第 {idx} 行：item_id 非法") from e

    item_ids = sorted({x for x in raw_item_ids if x > 0})
    items_map = await _load_items_map(session, item_ids)

    # ✅ 行级校验：商品存在、启用、且属于同一供应商
    for idx, raw in enumerate(lines, start=1):
        item_id = int(raw.get("item_id"))
        it = items_map.get(item_id)
        if it is None:
            raise ValueError(f"第 {idx} 行：商品不存在（item_id={item_id}）")

        if getattr(it, "enabled", True) is not True:
            raise ValueError(f"第 {idx} 行：商品已停用（item_id={item_id}）")

        it_supplier_id = getattr(it, "supplier_id", None)
        if it_supplier_id is None:
            raise ValueError(f"第 {idx} 行：商品未绑定供应商，禁止用于采购（item_id={item_id}）")

        if int(it_supplier_id) != int(po_supplier_id):
            raise ValueError(
                f"第 {idx} 行：商品不属于当前供应商（item_id={item_id}）"
            )

    norm_lines: List[Dict[str, Any]] = []
    total_amount = Decimal("0")

    for idx, raw in enumerate(lines, start=1):
        item_id = raw.get("item_id")
        qty_ordered = raw.get("qty_ordered")
        if item_id is None or qty_ordered is None:
            raise ValueError("每一行必须包含 item_id 与 qty_ordered")

        item_id = int(item_id)
        qty_ordered = int(qty_ordered)
        if qty_ordered <= 0:
            raise ValueError("行 qty_ordered 必须 > 0")

        supply_price = raw.get("supply_price")
        if supply_price is not None:
            supply_price = Decimal(str(supply_price))

        units_per_case = raw.get("units_per_case")
        units_per_case_int: Optional[int]
        if units_per_case is not None:
            units_per_case_int = int(units_per_case)
            if units_per_case_int <= 0:
                raise ValueError("units_per_case 必须为正整数")
        else:
            units_per_case_int = None

        line_no = raw.get("line_no") or idx

        line_amount_raw = raw.get("line_amount")
        if line_amount_raw is not None:
            line_amount = Decimal(str(line_amount_raw))
        elif supply_price is not None:
            multiplier = units_per_case_int or 1
            qty_units = qty_ordered * multiplier
            line_amount = supply_price * qty_units
        else:
            line_amount = None

        if line_amount is not None:
            total_amount += line_amount

        norm_lines.append(
            {
                "line_no": line_no,
                "item_id": item_id,
                "item_name": raw.get("item_name"),
                "item_sku": raw.get("item_sku"),
                "category": raw.get("category"),
                "spec_text": raw.get("spec_text"),
                "base_uom": raw.get("base_uom"),
                "purchase_uom": raw.get("purchase_uom"),
                "supply_price": supply_price,
                "retail_price": raw.get("retail_price"),
                "promo_price": raw.get("promo_price"),
                "min_price": raw.get("min_price"),
                "qty_cases": raw.get("qty_cases") or qty_ordered,
                "units_per_case": units_per_case_int,
                "qty_ordered": qty_ordered,
                "qty_received": 0,
                "line_amount": line_amount,
                "status": "CREATED",
                "remark": raw.get("remark"),
            }
        )

    po = PurchaseOrder(
        supplier=supplier.strip(),
        supplier_id=po_supplier_id,
        supplier_name=(supplier_name or supplier).strip(),
        warehouse_id=int(warehouse_id),
        purchaser=purchaser.strip(),
        purchase_time=purchase_time,
        total_amount=total_amount if total_amount != Decimal("0") else None,
        status="CREATED",
        remark=remark,
    )
    session.add(po)
    await session.flush()

    for nl in norm_lines:
        line = PurchaseOrderLine(
            po_id=po.id,
            line_no=nl["line_no"],
            item_id=nl["item_id"],
            item_name=nl["item_name"],
            item_sku=nl["item_sku"],
            category=nl["category"],
            spec_text=nl["spec_text"],
            base_uom=nl["base_uom"],
            purchase_uom=nl["purchase_uom"],
            supply_price=nl["supply_price"],
            retail_price=nl["retail_price"],
            promo_price=nl["promo_price"],
            min_price=nl["min_price"],
            qty_cases=nl["qty_cases"],
            units_per_case=nl["units_per_case"],
            qty_ordered=nl["qty_ordered"],
            qty_received=nl["qty_received"],
            line_amount=nl["line_amount"],
            status=nl["status"],
            remark=nl["remark"],
        )
        session.add(line)

    await session.flush()
    return po
