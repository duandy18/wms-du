# app/services/outbound_service.py
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock_service import StockService

UTC = timezone.utc

__all__ = ["ShipLine", "OutboundService", "ship_commit", "commit_outbound"]


@dataclass
class ShipLine:
    item_id: int
    batch_code: str
    qty: int
    warehouse_id: Optional[int] = None
    batch_id: Optional[int] = None
    meta: Optional[Dict[str, Any]] = None


class OutboundService:
    """
    Phase 3 出库服务（硬口径 + 强幂等）：

    - 粒度：(warehouse_id, item_id, batch_code)
    - 幂等：以 (ref=order_id, item_id, warehouse_id, batch_code) 为键，
      先查已扣数量，再扣“剩余需要扣”的量。
    - 同一 payload 中重复的 (item,wh,batch) 会先合并为一行，再做一次扣减。

    Phase 3.6：增加 trace_id 透传能力（当前不直接写 audit，仅向下传参）。
    Phase 3.7-A：trace_id 透传到 StockService.adjust，用于后续填充 stock_ledger.trace_id。

    Phase 3.9（Ship v3）：
    ----------------------
    出库成功后，自动将与 trace_id 对应的 open reservation_lines.consumed_qty 补齐，
    使“预占 → 出库”形成闭环。
    """

    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self.stock_svc = stock_svc or StockService()

    async def _consume_reservations_for_trace(
        self,
        session: AsyncSession,
        *,
        trace_id: Optional[str],
        shipped_by_item: Dict[int, int],
    ) -> None:
        """
        Ship v3: 自动消费预占（reservation_lines.consumed_qty）

        策略（保守版）：

        - 如果 trace_id 为空，直接跳过；
        - shipped_by_item: {item_id: 本次实际发货数量}；
        - 对每个 item_id：
            * 找到 trace_id 匹配且 status='open' 的 reservation_lines；
            * 按 created_at 顺序依次扣减 consumed_qty，最多扣到 shipped_qty；
        - 不修改 reservations.status，只调整 reservation_lines.consumed_qty。

        仅在出库成功（有实际 need>0）时才更新 shipped_by_item。
        """
        if not trace_id:
            return
        if not shipped_by_item:
            return

        for item_id, shipped_qty in shipped_by_item.items():
            remain = int(shipped_qty or 0)
            if remain <= 0:
                continue

            # 找到 trace_id + item_id 对应的 open reservation_lines
            res2 = await session.execute(
                sa.text(
                    """
                    SELECT rl.id,
                           rl.qty,
                           rl.consumed_qty
                      FROM reservation_lines rl
                      JOIN reservations r
                        ON r.id = rl.reservation_id
                     WHERE r.trace_id = :tid
                       AND r.status   = 'open'
                       AND rl.item_id = :item_id
                     ORDER BY rl.created_at ASC, rl.id ASC
                    """
                ),
                {"tid": trace_id, "item_id": item_id},
            )
            lines = res2.mappings().all()
            if not lines:
                continue

            for line in lines:
                line_id = int(line["id"])
                qty = int(line["qty"])
                consumed = int(line["consumed_qty"] or 0)
                open_qty = qty - consumed
                if open_qty <= 0:
                    continue

                take = min(open_qty, remain)
                if take <= 0:
                    break

                await session.execute(
                    sa.text(
                        """
                        UPDATE reservation_lines
                           SET consumed_qty = consumed_qty + :take,
                               updated_at   = now()
                         WHERE id = :id
                        """
                    ),
                    {"take": take, "id": line_id},
                )

                remain -= take
                if remain <= 0:
                    break

    async def commit(
        self,
        session: AsyncSession,
        *,
        order_id: str | int,
        lines: Sequence[Dict[str, Any] | ShipLine],
        occurred_at: Optional[datetime] = None,
        warehouse_code: Optional[str] = None,  # 保留旧签名，当前实现不使用
        trace_id: Optional[str] = None,  # 上层可携带 trace_id
    ) -> Dict[str, Any]:
        ts = occurred_at or datetime.now(UTC)
        if ts.tzinfo is None:
            ts = datetime.now(UTC)

        # 1) 归一化 + 合并：同一 (item_id, warehouse_id, batch_code) 汇总为一行
        agg_qty: Dict[Tuple[int, int, str], int] = defaultdict(int)
        for raw in lines:
            ln = self._coerce_line(raw)
            if ln.warehouse_id is None:
                raise ValueError("warehouse_id is required in each ship line")
            key = (int(ln.item_id), int(ln.warehouse_id), str(ln.batch_code))
            agg_qty[key] += int(ln.qty)

        committed = 0
        total_qty = 0
        results: List[Dict[str, Any]] = []

        # 记录本次实际发货量（按 item_id 聚合），供 Ship v3 消耗预占使用
        shipped_by_item: Dict[int, int] = defaultdict(int)

        # 2) 对每个合并后的槽位做一次“已扣 + 剩余扣减”逻辑
        for (item_id, wh_id, batch_code), want_qty in agg_qty.items():
            # 已扣数量（负数，例如 -3）
            row = await session.execute(
                sa.text(
                    """
                    SELECT COALESCE(SUM(delta), 0)
                    FROM stock_ledger
                    WHERE ref=:ref
                      AND item_id=:item
                      AND warehouse_id=:wid
                      AND batch_code=:code
                      AND delta < 0
                    """
                ),
                {"ref": str(order_id), "item": item_id, "wid": wh_id, "code": batch_code},
            )
            already = int(row.scalar() or 0)
            need = int(want_qty) + already  # 目标是总 delta = -want_qty

            if need <= 0:
                # 已经满足（或超扣，不太可能），视为幂等
                results.append(
                    {
                        "item_id": item_id,
                        "batch_code": batch_code,
                        "warehouse_id": wh_id,
                        "qty": int(want_qty),
                        "status": "OK",
                        "idempotent": True,
                    }
                )
                continue

            try:
                res = await self.stock_svc.adjust(
                    session=session,
                    item_id=item_id,
                    delta=-need,
                    reason="OUTBOUND_SHIP",
                    ref=str(order_id),
                    ref_line=1,  # 同一个 order_id 只占用一个 ref_line，幂等由 delta 汇总保证
                    occurred_at=ts,
                    warehouse_id=wh_id,
                    batch_code=batch_code,
                    trace_id=trace_id,  # Phase 3.7-A：trace_id 透传到底层 ledger 写入
                )
                committed += 1
                total_qty += need
                shipped_by_item[item_id] += need  # 记录本次实际发货量（Ship v3 使用）
                results.append(
                    {
                        "item_id": item_id,
                        "batch_code": batch_code,
                        "warehouse_id": wh_id,
                        "qty": need,
                        "status": "OK",
                        "after": res.get("after"),
                    }
                )
            except ValueError as e:
                results.append(
                    {
                        "item_id": item_id,
                        "batch_code": batch_code,
                        "warehouse_id": wh_id,
                        "qty": need,
                        "status": "INSUFFICIENT",
                        "error": str(e),
                    }
                )

        # 3) Ship v3：出库成功后，自动消费 trace 对应的预占
        try:
            await self._consume_reservations_for_trace(
                session=session,
                trace_id=trace_id,
                shipped_by_item=shipped_by_item,
            )
        except Exception:
            # 自动 consume 失败不能影响出库主流程；
            # 如需观察，可接入 event_log / logging 记录 warning。
            pass

        return {
            "status": "OK",
            "order_id": str(order_id),
            "total_qty": total_qty,
            "committed_lines": committed,
            "results": results,
            # trace_id 不放在返回体里，以免破坏现有 tests；
            # 如需关联，请通过 audit_events(meta.trace_id / trace_id) + ref 进行查询。
        }

    @staticmethod
    def _coerce_line(raw: Dict[str, Any] | ShipLine) -> ShipLine:
        if isinstance(raw, ShipLine):
            return raw
        return ShipLine(
            item_id=int(raw["item_id"]),
            batch_code=str(raw["batch_code"]),
            qty=int(raw["qty"]),
            warehouse_id=(
                int(raw["warehouse_id"])
                if "warehouse_id" in raw and raw["warehouse_id"] is not None
                else None
            ),
            batch_id=raw.get("batch_id"),
            meta=raw.get("meta"),
        )


# 便捷函数（与历史签名兼容）
async def ship_commit(
    session: AsyncSession,
    order_id: str | int,
    lines: Sequence[Dict[str, Any] | ShipLine],
    warehouse_code: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
    trace_id: Optional[str] = None,  # HTTP / API 层可直接传 trace_id
) -> Dict[str, Any]:
    svc = OutboundService()
    return await svc.commit(
        session=session,
        order_id=order_id,
        lines=lines,
        warehouse_code=warehouse_code,
        occurred_at=occurred_at,
        trace_id=trace_id,
    )


# 历史别名
commit_outbound = ship_commit
