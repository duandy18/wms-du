# app/wms/procurement/services/purchase_order_receive_workbench_canon.py
from __future__ import annotations

from typing import Dict, List

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lot import Lot
from app.models.stock_ledger import StockLedger
from app.wms.procurement.contracts.purchase_order_receive_workbench import WorkbenchBatchRowOut


async def fill_canonical_lot_dates(
    session: AsyncSession,
    *,
    warehouse_id: int,
    po_line_to_item_id: Dict[int, int],
    batches_map: Dict[int, List[WorkbenchBatchRowOut]],
) -> None:
    """
    将 WorkbenchBatchRowOut.production_date/expiry_date 回填为 canonical
    （来自 lots + stock_ledger(reason_canon='RECEIPT')）。

    合同：
    - lot_code=None => prod/exp 必须为 None
    - lot_code!=None => 先按 (warehouse_id, item_id, lot_code) 定位 lots，
      再从 stock_ledger 的 RECEIPT 时间事实回填 production_date/expiry_date
    """
    need_pairs: set[tuple[int, str]] = set()
    for po_line_id, xs in batches_map.items():
        item_id = po_line_to_item_id.get(int(po_line_id))
        if not item_id:
            continue
        for b in xs:
            lot_code = getattr(b, "lot_code", None)
            if lot_code is None:
                continue
            need_pairs.add((int(item_id), str(lot_code)))

    canon_map: Dict[tuple[int, str], tuple[object | None, object | None]] = {}
    if need_pairs:
        stmt = (
            select(
                Lot.item_id,
                Lot.lot_code,
                sa.func.max(StockLedger.production_date).label("production_date"),
                sa.func.max(StockLedger.expiry_date).label("expiry_date"),
            )
            .select_from(Lot)
            .join(
                StockLedger,
                sa.and_(
                    StockLedger.lot_id == Lot.id,
                    StockLedger.warehouse_id == Lot.warehouse_id,
                    StockLedger.item_id == Lot.item_id,
                    StockLedger.reason_canon == "RECEIPT",
                ),
            )
            .where(Lot.warehouse_id == int(warehouse_id))
            .where(sa.tuple_(Lot.item_id, Lot.lot_code).in_(list(need_pairs)))
            .group_by(Lot.item_id, Lot.lot_code)
        )
        rows = (await session.execute(stmt)).all()
        for item_id, lot_code, production_date, expiry_date in rows:
            if lot_code is None:
                continue
            canon_map[(int(item_id), str(lot_code))] = (production_date, expiry_date)

    for po_line_id, xs in batches_map.items():
        item_id = po_line_to_item_id.get(int(po_line_id))
        for b in xs:
            lot_code = getattr(b, "lot_code", None)
            if lot_code is None or not item_id:
                b.production_date = None
                b.expiry_date = None
                continue
            production_date, expiry_date = canon_map.get((int(item_id), str(lot_code)), (None, None))
            b.production_date = production_date
            b.expiry_date = expiry_date
