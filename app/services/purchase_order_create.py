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
from app.models.supplier import Supplier


async def _load_items_map(session: AsyncSession, item_ids: List[int]) -> Dict[int, Item]:
    if not item_ids:
        return {}
    rows = (await session.execute(select(Item).where(Item.id.in_(item_ids)))).scalars().all()
    return {int(it.id): it for it in rows}


async def _require_supplier_for_po(session: AsyncSession, supplier_id: Optional[int]) -> Supplier:
    if supplier_id is None:
        raise ValueError("supplier_id 不能为空：采购单必须绑定供应商")
    sid = int(supplier_id)
    if sid <= 0:
        raise ValueError("supplier_id 非法：采购单必须绑定供应商")

    supplier = (
        (await session.execute(select(Supplier).where(Supplier.id == sid))).scalars().first()
    )
    if supplier is None:
        raise ValueError(f"supplier_id 不存在：未找到供应商（supplier_id={sid}）")

    # 可选：如果你们有 active 字段且要硬闸，可以放开下面逻辑
    # if getattr(supplier, "active", True) is not True:
    #     raise ValueError("供应商已停用，禁止创建采购单")

    return supplier


def _safe_upc(v: Optional[int]) -> int:
    try:
        n = int(v or 1)
    except Exception:
        n = 1
    return n if n > 0 else 1


def _trim_or_none(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _parse_discount_amount(v: Any) -> Decimal:
    if v is None or (isinstance(v, str) and not v.strip()):
        return Decimal("0")
    try:
        d = Decimal(str(v))
    except Exception as e:
        raise ValueError("discount_amount 必须为数字") from e
    if d < 0:
        raise ValueError("discount_amount 必须 >= 0")
    return d


async def create_po_v2(
    session: AsyncSession,
    *,
    supplier_id: int,
    warehouse_id: int,
    purchaser: str,
    purchase_time: datetime,
    remark: Optional[str] = None,
    lines: List[Dict[str, Any]],
) -> PurchaseOrder:
    """
    创建“头 + 多行”的采购单。

    ✅ 数量合同（方案 A）：
    - qty_ordered: 采购单位订购量（输入快照）
    - units_per_case: 换算因子（每采购单位包含多少最小单位，>0，默认 1）
    - qty_ordered_base: 最小单位订购量（事实字段，唯一口径）
      * 由 qty_ordered 与 units_per_case 在写入阶段计算得到（计算逻辑集中在服务层）

    ✅ 价格合同：
    - supply_price: 按 base_uom 计价的采购单价快照（可空）
    - discount_amount: 整行减免金额（>=0）
    - discount_note: 折扣说明（可选）
    - 行金额不落库；PO.total_amount 在创建时可按可计算行聚合写入

    ✅ 封板规则（关键）：
    - item_name / item_sku 必须由后端从 Item 主数据生成写入 purchase_order_lines（行快照）
    - 不允许前端传入/覆盖（避免第二真相入口）

    ✅ 供应商规则（关键）：
    - 废除 supplier 自由文本列：只接受 supplier_id
    - supplier_name 由后端从 suppliers 表取值并写快照（必填）
    """
    if not lines:
        raise ValueError("create_po_v2 需要至少一行行项目（lines 不可为空）")

    if not purchaser or not purchaser.strip():
        raise ValueError("采购人 purchaser 不能为空")

    if not isinstance(purchase_time, datetime):
        raise ValueError("purchase_time 必须为 datetime 类型")

    # ✅ 采购事实硬闸：采购单必须绑定供应商（并且 supplier 必须存在）
    supplier_obj = await _require_supplier_for_po(session, supplier_id)
    po_supplier_id = int(getattr(supplier_obj, "id"))
    po_supplier_name = str(getattr(supplier_obj, "name") or "").strip()
    if not po_supplier_name:
        raise ValueError("供应商名称为空，禁止创建采购单（suppliers.name 不能为空）")

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
            raise ValueError(f"第 {idx} 行：商品不属于当前供应商（item_id={item_id}）")

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

        it = items_map.get(item_id)
        if it is None:
            raise ValueError(f"第 {idx} 行：商品不存在（item_id={item_id}）")

        supply_price = raw.get("supply_price")
        if supply_price is not None and not (isinstance(supply_price, str) and not supply_price.strip()):
            supply_price = Decimal(str(supply_price))
        else:
            supply_price = None

        units_per_case = raw.get("units_per_case")
        units_per_case_int: Optional[int]
        if units_per_case is not None:
            units_per_case_int = int(units_per_case)
            if units_per_case_int <= 0:
                raise ValueError("units_per_case 必须为正整数")
        else:
            units_per_case_int = None

        upc = _safe_upc(units_per_case_int)

        # ✅ 最小单位订购量（事实字段）
        qty_ordered_base = qty_ordered * upc
        if qty_ordered_base <= 0:
            raise ValueError("行 qty_ordered_base 必须 > 0")

        line_no = raw.get("line_no") or idx

        discount_amount = _parse_discount_amount(raw.get("discount_amount"))
        discount_note = _trim_or_none(raw.get("discount_note"))

        # 如果给了折扣但没价格，无法复算金额，直接拒绝（避免脏合同）
        if discount_amount > 0 and supply_price is None:
            raise ValueError("存在折扣时必须提供 supply_price（按 base_uom 单价）")

        # ✅ 计算行金额（不落库）：用于 PO.total_amount 的创建聚合
        # 规则：supply_price 为空 -> 按 0 计；保证 total_amount 永不为 NULL
        line_total = (Decimal("0") if supply_price is None else (supply_price * Decimal(int(qty_ordered_base)))) - discount_amount
        if line_total < 0:
            raise ValueError("折扣金额超出行金额，导致行金额为负")
        total_amount += line_total

        # ✅ 封板：行快照字段来自 Item 主数据
        item_name_snapshot = _trim_or_none(getattr(it, "name", None))
        item_sku_snapshot = _trim_or_none(getattr(it, "sku", None))

        norm_lines.append(
            {
                "line_no": int(line_no),
                "item_id": item_id,
                "item_name": item_name_snapshot,
                "item_sku": item_sku_snapshot,
                "spec_text": _trim_or_none(raw.get("spec_text")),
                "base_uom": _trim_or_none(raw.get("base_uom")),
                "purchase_uom": _trim_or_none(raw.get("purchase_uom")),
                "supply_price": supply_price,
                "units_per_case": upc,  # ✅ 直接写非空 upc
                "qty_ordered": qty_ordered,
                "qty_ordered_base": qty_ordered_base,
                "discount_amount": discount_amount,
                "discount_note": discount_note,
                "remark": raw.get("remark"),
            }
        )

    po = PurchaseOrder(
        supplier_id=po_supplier_id,
        supplier_name=po_supplier_name,
        warehouse_id=int(warehouse_id),
        purchaser=purchaser.strip(),
        purchase_time=purchase_time,
        total_amount=total_amount,  # ✅ 永不返回 None（避免 UI/报表到处判空）
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
            spec_text=nl["spec_text"],
            base_uom=nl["base_uom"],
            purchase_uom=nl["purchase_uom"],
            supply_price=nl["supply_price"],
            units_per_case=nl["units_per_case"],
            qty_ordered=nl["qty_ordered"],
            qty_ordered_base=nl["qty_ordered_base"],
            discount_amount=nl["discount_amount"],
            discount_note=nl["discount_note"],
            remark=nl["remark"],
        )
        session.add(line)

    await session.flush()
    return po
