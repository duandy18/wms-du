# app/services/purchase_order_service.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import MovementType
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.services.inbound_service import InboundService

UTC = timezone.utc


class PurchaseOrderService:
    """
    采购单服务（Phase 2：唯一形态）

    - create_po_v2: 创建“头 + 多行”的采购单；
    - get_po_with_lines: 获取带行的采购单（头 + 行）；
    - receive_po_line: 针对某一行执行收货，并更新头表状态。

    金额约定（非常重要）：

    - qty_ordered：订购“件数”（采购单位，如 件/箱）
    - units_per_case：每件包含的最小单位数量（如每箱 8 袋）
    - supply_price：采购价格，按“最小单位”计价（单袋价格）
    - 行金额 line_amount = qty_ordered × units_per_case × supply_price
      若 units_per_case 为空，则退化为 qty_ordered × supply_price
    - total_amount = 所有行 line_amount 的和
    """

    def __init__(self, inbound_svc: Optional[InboundService] = None) -> None:
        self.inbound_svc = inbound_svc or InboundService()

    # ------------------ 创建：头 + 多行 ------------------ #

    async def create_po_v2(
        self,
        session: AsyncSession,
        *,
        supplier: str,
        warehouse_id: int,
        supplier_id: Optional[int] = None,
        supplier_name: Optional[str] = None,
        remark: Optional[str] = None,
        lines: List[Dict[str, Any]],
    ) -> PurchaseOrder:
        """
        创建“头 + 多行”的采购单。

        约定：
        - lines 至少一行；
        - 每行必须包含 item_id, qty_ordered；
        - 行内价格体系（supply_price 等）可选；
        - 头表 total_amount = 行 line_amount 求和：
            * 首选使用传入的 line_amount；
            * 否则按 qty_ordered × units_per_case × supply_price 计算；
            * 若 units_per_case 为空，则退化为 qty_ordered × supply_price。
        """
        if not lines:
            raise ValueError("create_po_v2 需要至少一行行项目（lines 不可为空）")

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

            # 采购价格：按“最小单位”计价
            supply_price = raw.get("supply_price")
            if supply_price is not None:
                supply_price = Decimal(str(supply_price))

            # 每件包含的最小单位数量
            units_per_case = raw.get("units_per_case")
            units_per_case_int: Optional[int]
            if units_per_case is not None:
                units_per_case_int = int(units_per_case)
                if units_per_case_int <= 0:
                    raise ValueError("units_per_case 必须为正整数")
            else:
                units_per_case_int = None

            # 行号：允许前端传 line_no，否则默认使用顺序 idx
            line_no = raw.get("line_no") or idx

            # 行金额计算：
            # - 如果传入了 line_amount：直接使用；
            # - 否则：
            #   * 若有 supply_price 和 units_per_case：qty_ordered × units_per_case × supply_price；
            #   * 若只有 supply_price：qty_ordered × supply_price；
            #   * 否则为 None。
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
                    # 数量体系
                    "qty_cases": raw.get("qty_cases") or qty_ordered,
                    "units_per_case": units_per_case_int,
                    "qty_ordered": qty_ordered,
                    "qty_received": 0,
                    # 金额 & 状态
                    "line_amount": line_amount,
                    "status": "CREATED",
                    "remark": raw.get("remark"),
                }
            )

        po = PurchaseOrder(
            supplier=supplier.strip(),
            supplier_id=supplier_id,
            supplier_name=(supplier_name or supplier).strip(),
            warehouse_id=int(warehouse_id),
            total_amount=total_amount if total_amount != Decimal("0") else None,
            status="CREATED",
            remark=remark,
        )
        session.add(po)
        await session.flush()  # 让 po.id 生效

        # 创建行记录
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

    # ------------------ 查询：头 + 行 ------------------ #

    async def get_po_with_lines(
        self,
        session: AsyncSession,
        po_id: int,
        *,
        for_update: bool = False,
    ) -> Optional[PurchaseOrder]:
        """
        获取带行的采购单（头 + 行）。

        - 使用 selectinload 预加载 lines；
        - 行按 line_no 排序。
        """
        stmt = (
            select(PurchaseOrder)
            .options(selectinload(PurchaseOrder.lines))
            .where(PurchaseOrder.id == po_id)
        )
        if for_update:
            stmt = stmt.with_for_update()

        res = await session.execute(stmt)
        po = res.scalars().first()
        if po is None:
            return None

        if po.lines:
            po.lines.sort(key=lambda line: (line.line_no, line.id))
        return po

    # ------------------ 行级收货 ------------------ #

    async def receive_po_line(
        self,
        session: AsyncSession,
        *,
        po_id: int,
        line_id: Optional[int] = None,
        line_no: Optional[int] = None,
        qty: int,
        occurred_at: Optional[datetime] = None,
    ) -> PurchaseOrder:
        """
        对某一行执行收货（行级收货）。

        约定：
        - qty > 0；
        - line_id 和 line_no 至少提供一个（优先 line_id）；
        - 不允许行级超收；
        - ref = PO-{id}；
        - ref_line 仍采用“查 max(ref_line)+1”的方式，保持与现有 ledger 兼容。
        """
        if qty <= 0:
            raise ValueError("收货数量 qty 必须 > 0")
        if line_id is None and line_no is None:
            raise ValueError("receive_po_line 需要提供 line_id 或 line_no 之一")

        po = await self.get_po_with_lines(session, po_id, for_update=True)
        if po is None:
            raise ValueError(f"PurchaseOrder not found: id={po_id}")

        if not po.lines:
            raise ValueError(f"采购单 {po_id} 没有任何行，无法执行行级收货")

        # 查找目标行
        target: Optional[PurchaseOrderLine] = None
        if line_id is not None:
            for line in po.lines:
                if line.id == line_id:
                    target = line
                    break
        elif line_no is not None:
            for line in po.lines:
                if line.line_no == line_no:
                    target = line
                    break

        if target is None:
            raise ValueError(
                f"在采购单 {po_id} 中未找到匹配的行 (line_id={line_id}, line_no={line_no})"
            )

        if target.status in {"RECEIVED", "CLOSED"}:
            raise ValueError(
                f"行已收完或已关闭，无法再收货 (line_id={target.id}, status={target.status})"
            )

        remaining = target.qty_ordered - target.qty_received
        if qty > remaining:
            raise ValueError(
                f"行收货数量超出剩余数量：ordered={target.qty_ordered}, "
                f"received={target.qty_received}, try_receive={qty}"
            )

        # ref 仍然复用 PO- 前缀
        ref = f"PO-{po.id}"
        reason_val = MovementType.INBOUND.value

        row = await session.execute(
            text(
                """
                SELECT COALESCE(MAX(ref_line), 0)
                  FROM stock_ledger
                 WHERE ref = :ref
                   AND reason = :reason
                   AND warehouse_id = :wid
                   AND item_id = :item_id
                """
            ),
            {
                "ref": ref,
                "reason": reason_val,
                "wid": po.warehouse_id,
                "item_id": target.item_id,
            },
        )
        max_ref_line = int(row.scalar() or 0)
        next_ref_line = max_ref_line + 1

        await self.inbound_svc.receive(
            session,
            qty=int(qty),
            ref=ref,
            ref_line=next_ref_line,
            warehouse_id=po.warehouse_id,
            item_id=target.item_id,
            occurred_at=occurred_at or datetime.now(UTC),
        )

        # 更新行状态
        target.qty_received += int(qty)
        now = datetime.now(UTC)

        if target.qty_received == 0:
            target.status = "CREATED"
        elif target.qty_received < target.qty_ordered:
            target.status = "PARTIAL"
        elif target.qty_received == target.qty_ordered:
            target.status = "RECEIVED"
        else:
            target.status = "CLOSED"

        # 头表状态 = 聚合行状态
        all_zero = all(line.qty_received == 0 for line in po.lines)
        all_full = all(line.qty_received >= line.qty_ordered for line in po.lines)

        if all_zero:
            po.status = "CREATED"
            po.closed_at = None
        elif all_full:
            po.status = "RECEIVED"
            po.closed_at = now
        else:
            po.status = "PARTIAL"
            po.closed_at = None

        po.last_received_at = now

        await session.flush()
        return po
