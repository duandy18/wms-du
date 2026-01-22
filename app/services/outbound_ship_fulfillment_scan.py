# app/services/outbound_ship_fulfillment_scan.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock_availability_service import StockAvailabilityService


@dataclass(frozen=True)
class OrderNeedLine:
    item_id: int
    qty: int


@dataclass(frozen=True)
class MissingLine:
    item_id: int
    need: int
    available: int

    def to_dict(self) -> Dict[str, Any]:
        return {"item_id": int(self.item_id), "need": int(self.need), "available": int(self.available)}


@dataclass(frozen=True)
class WarehouseScanRow:
    warehouse_id: int
    status: str  # OK / INSUFFICIENT
    missing: Tuple[MissingLine, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "warehouse_id": int(self.warehouse_id),
            "status": str(self.status),
            "missing": [m.to_dict() for m in self.missing],
        }


def aggregate_needs(lines: Sequence[Dict[str, Any]]) -> List[OrderNeedLine]:
    """
    将 items 聚合为整单需求：[{item_id, qty}] -> List[OrderNeedLine]
    """
    m: Dict[int, int] = {}
    for it in lines or []:
        try:
            item_id = int(it.get("item_id"))
            qty = int(it.get("qty") or 0)
        except Exception:
            continue
        if item_id <= 0 or qty <= 0:
            continue
        m[item_id] = m.get(item_id, 0) + qty
    return [OrderNeedLine(item_id=k, qty=v) for k, v in sorted(m.items(), key=lambda kv: kv[0])]


async def scan_candidate_warehouses(
    *,
    session: AsyncSession,
    platform: str,
    shop_id: str,
    candidate_warehouse_ids: Sequence[int],
    needs: Sequence[OrderNeedLine],
) -> List[WarehouseScanRow]:
    """
    对候选仓做“整单同仓可履约扫描”：
    - 不选仓、不兜底、不写库
    - 输出 OK/INSUFFICIENT + 缺口明细
    - 事实源：StockAvailabilityService.get_available_for_item
    """
    rows: List[WarehouseScanRow] = []
    for wid_raw in candidate_warehouse_ids or []:
        wid = int(wid_raw)
        if wid <= 0:
            continue

        missing: List[MissingLine] = []
        for line in needs or []:
            if int(line.qty) <= 0:
                continue

            available_raw = await StockAvailabilityService.get_available_for_item(
                session,
                platform=str(platform),
                shop_id=str(shop_id),
                warehouse_id=int(wid),
                item_id=int(line.item_id),
            )
            available = int(available_raw or 0)
            if available < 0:
                available = 0

            if int(line.qty) > available:
                missing.append(MissingLine(item_id=int(line.item_id), need=int(line.qty), available=int(available)))

        status = "OK" if not missing else "INSUFFICIENT"
        rows.append(WarehouseScanRow(warehouse_id=int(wid), status=status, missing=tuple(missing)))

    return rows
