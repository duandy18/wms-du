# app/services/purchase_order_receive_workbench_canon.py
from __future__ import annotations

from typing import Dict, List

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.batch import Batch
from app.schemas.purchase_order_receive_workbench import WorkbenchBatchRowOut


async def fill_canonical_batch_dates(
    session: AsyncSession,
    *,
    warehouse_id: int,
    po_line_to_item_id: Dict[int, int],
    batches_map: Dict[int, List[WorkbenchBatchRowOut]],
) -> None:
    """
    将 WorkbenchBatchRowOut.production_date/expiry_date 回填为 canonical（来自 batches）。
    合同：
    - batch_code=None => prod/exp 必须为 None
    - batch_code!=None => 从 batches(item_id, warehouse_id, batch_code) 精确匹配
    """
    need_pairs: set[tuple[int, str]] = set()
    for po_line_id, xs in batches_map.items():
        item_id = po_line_to_item_id.get(int(po_line_id))
        if not item_id:
            continue
        for b in xs:
            bc = getattr(b, "batch_code", None)
            if bc is None:
                continue
            need_pairs.add((int(item_id), str(bc)))

    canon_map: Dict[tuple[int, str], tuple[object | None, object | None]] = {}
    if need_pairs:
        stmt = (
            select(Batch.item_id, Batch.batch_code, Batch.production_date, Batch.expiry_date)
            .where(Batch.warehouse_id == int(warehouse_id))
            .where(sa.tuple_(Batch.item_id, Batch.batch_code).in_(list(need_pairs)))
        )
        rows = (await session.execute(stmt)).all()
        for item_id, batch_code, pd, ed in rows:
            canon_map[(int(item_id), str(batch_code))] = (pd, ed)

    for po_line_id, xs in batches_map.items():
        item_id = po_line_to_item_id.get(int(po_line_id))
        for b in xs:
            bc = getattr(b, "batch_code", None)
            if bc is None or not item_id:
                b.production_date = None
                b.expiry_date = None
                continue
            pd, ed = canon_map.get((int(item_id), str(bc)), (None, None))
            b.production_date = pd
            b.expiry_date = ed
