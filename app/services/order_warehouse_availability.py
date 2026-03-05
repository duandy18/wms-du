# app/services/order_warehouse_availability.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock_availability_service import StockAvailabilityService


@dataclass(frozen=True)
class AvailabilityLine:
    item_id: int
    req_qty: int
    sku_id: Optional[str] = None
    title: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "item_id": int(self.item_id),
            "req_qty": int(self.req_qty),
            "sku_id": str(self.sku_id) if self.sku_id is not None else None,
            "title": str(self.title) if self.title is not None else None,
        }


@dataclass(frozen=True)
class AvailabilityCell:
    warehouse_id: int
    item_id: int
    available: int
    shortage: int
    status: str  # ENOUGH | SHORTAGE

    def to_dict(self) -> dict:
        return {
            "warehouse_id": int(self.warehouse_id),
            "item_id": int(self.item_id),
            "available": int(self.available),
            "shortage": int(self.shortage),
            "status": str(self.status),
        }


class OrderWarehouseAvailabilityService:
    """
    Phase 5.3 Explain（解释层 / 对齐层）：
    - 不裁决（不改变 AUTO/MANUAL 逻辑）
    - 不写库
    - 输出：订单需求（按 item 聚合）× 仓库可售（事实层）
    """

    @staticmethod
    async def load_order_need_lines(
        session: AsyncSession,
        *,
        order_id: int,
    ) -> Tuple[AvailabilityLine, ...]:
        rows = await session.execute(
            text(
                """
                SELECT
                  item_id,
                  SUM(COALESCE(qty, 0)) AS req_qty,
                  MAX(sku_id) AS sku_id,
                  MAX(title)  AS title
                FROM order_items
                WHERE order_id = :oid
                GROUP BY item_id
                ORDER BY item_id
                """
            ),
            {"oid": int(order_id)},
        )

        def _norm_str(v: Optional[str]) -> Optional[str]:
            if v is None:
                return None
            s = str(v).strip()
            return s if s else None

        out: List[AvailabilityLine] = []
        for item_id, req_qty, sku_id, title in rows.fetchall():
            q = int(req_qty or 0)
            if int(item_id) <= 0 or q <= 0:
                continue
            out.append(
                AvailabilityLine(
                    item_id=int(item_id),
                    req_qty=q,
                    sku_id=_norm_str(sku_id),
                    title=_norm_str(title),
                )
            )
        return tuple(out)

    @staticmethod
    async def build_matrix(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        order_id: int,
        warehouse_ids: Sequence[int],
    ) -> Tuple[Tuple[AvailabilityLine, ...], Tuple[AvailabilityCell, ...]]:
        lines = await OrderWarehouseAvailabilityService.load_order_need_lines(session, order_id=order_id)
        if not lines:
            return tuple(), tuple()

        whs: List[int] = []
        seen: set[int] = set()
        for w in warehouse_ids or []:
            wid = int(w)
            if wid <= 0 or wid in seen:
                continue
            seen.add(wid)
            whs.append(wid)

        if not whs:
            return lines, tuple()

        item_ids = [int(x.item_id) for x in lines]
        need_by_item: Dict[int, int] = {int(x.item_id): int(x.req_qty) for x in lines}

        cells: List[AvailabilityCell] = []
        for wid in whs:
            avail_map = await StockAvailabilityService.get_available_for_items(
                session,
                platform=str(platform),
                shop_id=str(shop_id),
                warehouse_id=int(wid),
                item_ids=item_ids,
            )
            for item_id in item_ids:
                need = int(need_by_item.get(int(item_id), 0))
                raw_avail = int(avail_map.get(int(item_id), 0))
                available = raw_avail if raw_avail >= 0 else 0  # 展示层可理解值
                shortage = max(need - available, 0)
                status = "ENOUGH" if shortage == 0 else "SHORTAGE"
                cells.append(
                    AvailabilityCell(
                        warehouse_id=int(wid),
                        item_id=int(item_id),
                        available=int(available),
                        shortage=int(shortage),
                        status=status,
                    )
                )

        return lines, tuple(cells)
