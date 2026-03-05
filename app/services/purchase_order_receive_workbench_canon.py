# app/services/purchase_order_receive_workbench_canon.py
from __future__ import annotations

from typing import Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.purchase_order_receive_workbench import WorkbenchBatchRowOut


async def fill_canonical_lot_dates(
    session: AsyncSession,
    *,
    warehouse_id: int,
    po_line_to_item_id: Dict[int, int],
    batch_rows_map: Dict[int, List[WorkbenchBatchRowOut]],
) -> None:
    """
    将 WorkbenchBatchRowOut.production_date/expiry_date 回填为 canonical（来自 receipt_lines 日期事实）。

    合同：
    - batch_code=None => prod/exp 必须为 None
    - batch_code!=None => 从 inbound_receipt_lines(warehouse_id,item_id,lot_code_input) 精确匹配/聚合得到日期事实
    """
    need_pairs: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()

    for po_line_id, xs in batch_rows_map.items():
        item_id = po_line_to_item_id.get(int(po_line_id))
        if not item_id:
            continue
        for b in xs:
            bc = getattr(b, "batch_code", None)
            if bc is None:
                continue
            key = (int(item_id), str(bc))
            if key in seen:
                continue
            seen.add(key)
            need_pairs.append(key)

    canon_map: Dict[tuple[int, str], tuple[object | None, object | None]] = {}
    if need_pairs:
        # psycopg 不支持把“tuple 列表”作为单个 bind 参数塞进 (a,b) IN :pairs
        # 这里把 IN 列表展开为 ((:i0,:c0),(:i1,:c1),...) 形式，避免语法错误且无注入风险
        in_terms: list[str] = []
        params: dict[str, object] = {"w": int(warehouse_id)}

        for idx, (iid, code) in enumerate(need_pairs):
            pi = f"i{idx}"
            pc = f"c{idx}"
            in_terms.append(f"(:{pi}, :{pc})")
            params[pi] = int(iid)
            params[pc] = str(code)

        # Lot-World 终态：日期事实在 inbound_receipt_lines（production_date/expiry_date）
        # 这里按 (warehouse_id,item_id,lot_code_input) 聚合出 canonical 日期（MAX 作为稳定聚合策略）
        sql = f"""
            SELECT
              rl.item_id,
              rl.lot_code_input AS lot_code,
              MAX(rl.production_date) AS production_date,
              MAX(rl.expiry_date)     AS expiry_date
            FROM inbound_receipt_lines rl
            WHERE rl.warehouse_id = :w
              AND rl.lot_code_input IS NOT NULL
              AND (rl.item_id, rl.lot_code_input) IN ({", ".join(in_terms)})
            GROUP BY rl.item_id, rl.lot_code_input
        """

        rows = (await session.execute(text(sql), params)).fetchall()
        for item_id, lot_code, pd, ed in rows:
            canon_map[(int(item_id), str(lot_code))] = (pd, ed)

    for po_line_id, xs in batch_rows_map.items():
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


# 兼容旧入口（避免上游没同步时直接炸）
async def fill_canonical_batch_dates(
    session: AsyncSession,
    *,
    warehouse_id: int,
    po_line_to_item_id: Dict[int, int],
    batch_rows_map: Dict[int, List[WorkbenchBatchRowOut]],
) -> None:
    await fill_canonical_lot_dates(
        session,
        warehouse_id=warehouse_id,
        po_line_to_item_id=po_line_to_item_id,
        batch_rows_map=batch_rows_map,
    )
