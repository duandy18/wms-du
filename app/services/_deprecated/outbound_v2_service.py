from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbound_v2 import OutboundCommitV2, OutboundLineV2
from app.services.stock_service import StockService

UTC = timezone.utc


@dataclass
class OutboundV2LineIn:
    warehouse_id: int
    item_id: int
    batch_code: str
    qty: int


class OutboundV2Service:
    """
    Outbound v2 服务（Phase 3.7-B）：

    - 头表 outbound_commits_v2 用于记录一次出库提交；
    - 明细表 outbound_lines_v2 记录每一个扣减槽位 (warehouse, item, batch);
    - 扣减逻辑统一走 StockService.adjust，保证 ledger 与 stocks 一致；
    - trace_id：
        * commit.trace_id = trace_id
        * lines.ledger_trace_id = trace_id
        * StockService.adjust 同步写入 stock_ledger.trace_id

    幂等：
      - 以 (platform, shop_id, ref) 为 commit 幂等键：
          * 若已存在 commit，则视为幂等返回；
          * 明细与库存幂等由 StockService 自己控制（按 ref + item 聚合）。
    """

    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self.stock_svc = stock_svc or StockService()

    async def _consume_reservations_for_trace(
        self,
        session: AsyncSession,
        *,
        trace_id: Optional[str],
    ) -> None:
        """
        出库后自动消费软预占（reservation_lines.consumed_qty）。

        策略（简化版）：
        - 若 trace_id 为空，则直接跳过；
        - 按 trace_id 找到所有 status='open' 的 reservations；
        - 按 lines 中 item_id 汇总本次出库数量，逐行消耗 reservation_lines。
        """
        if not trace_id:
            return

        # 1) 聚合本次 trace 对应的出库数量（按 item_id 汇总）
        res = await session.execute(
            text(
                """
                SELECT item_id, SUM(qty) AS shipped_qty
                  FROM outbound_lines_v2
                 WHERE ledger_trace_id = :tid
                 GROUP BY item_id
                """
            ),
            {"tid": trace_id},
        )
        shipped_rows = res.mappings().all()
        if not shipped_rows:
            return

        # 2) 找到 trace_id 下的 open reservations + reservation_lines
        res2 = await session.execute(
            text(
                """
                SELECT rl.id,
                       rl.qty,
                       rl.consumed_qty,
                       rl.item_id
                  FROM reservation_lines rl
                  JOIN reservations r
                    ON r.id = rl.reservation_id
                 WHERE r.trace_id = :tid
                   AND r.status   = 'open'
                 ORDER BY rl.item_id, rl.created_at, rl.id
                """
            ),
            {"tid": trace_id},
        )
        lines = res2.mappings().all()
        if not lines:
            return

        # 按 item_id 分桶 reservation_lines
        bucket: Dict[int, List[Dict[str, Any]]] = {}
        for row in lines:
            item_id = int(row["item_id"])
            bucket.setdefault(item_id, []).append(row)

        # 3) 对每个 item_id 消耗 reservation_lines.consumed_qty
        for row in shipped_rows:
            item_id = int(row["item_id"])
            remain = int(row["shipped_qty"] or 0)
            if remain <= 0:
                continue

            if item_id not in bucket:
                continue

            for line in bucket[item_id]:
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
                    text(
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
        trace_id: str,
        platform: str,
        shop_id: str,
        ref: str,
        external_order_ref: Optional[str] = None,
        lines: Sequence[Mapping[str, Any] | OutboundV2LineIn] = (),
        occurred_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        执行一次 v2 出库：

        - trace_id: 全链 trace 主键（必填）；
        - platform/shop_id/ref: 业务键；
        - external_order_ref: 可选，记录平台订单号；
        - lines: [{warehouse_id, item_id, batch_code, qty}, ...]

        幂等规则：
        - 若此前已有 (platform, shop_id, ref) 对应的 commit，则视为幂等：
          * 不再新增头表记录；
          * 明细与扣减由 StockService.adjust 保证幂等。
        """
        if not trace_id:
            raise ValueError("trace_id is required for OutboundV2Service.commit")

        plat = platform.upper()
        ts = occurred_at or datetime.now(UTC)
        if ts.tzinfo is None:
            ts = datetime.now(UTC)

        # 1) 聚合行：同一 (wh,item,batch) 汇总 qty
        agg: Dict[Tuple[int, int, str], int] = {}
        for raw in lines or ():
            if isinstance(raw, OutboundV2LineIn):
                wh_id = int(raw.warehouse_id)
                item_id = int(raw.item_id)
                code = str(raw.batch_code)
                qty = int(raw.qty)
            else:
                wh_id = int(raw["warehouse_id"])
                item_id = int(raw["item_id"])
                code = str(raw["batch_code"])
                qty = int(raw["qty"])
            if qty <= 0:
                continue
            key = (wh_id, item_id, code)
            agg[key] = agg.get(key, 0) + qty

        if not agg:
            return {
                "status": "NO_LINES",
                "commit_id": None,
                "total_qty": 0,
                "idempotent": True,
                "results": [],
            }

        # 2) 查是否已有 commit（幂等）
        res_commit = await session.execute(
            text(
                """
                SELECT id
                  FROM outbound_commits_v2
                 WHERE platform = :p
                   AND shop_id  = :s
                   AND ref      = :r
                 LIMIT 1
                """
            ),
            {"p": plat, "s": shop_id, "r": ref},
        )
        row_commit = res_commit.first()
        idempotent = row_commit is not None

        if row_commit:
            commit_id = int(row_commit[0])
        else:
            commit = OutboundCommitV2(
                trace_id=trace_id,
                platform=plat,
                shop_id=shop_id,
                ref=ref,
                external_order_ref=external_order_ref,
                state="COMPLETED",
                created_at=ts,
                updated_at=ts,
            )
            session.add(commit)
            await session.flush()
            commit_id = int(commit.id)

        total_qty = 0
        results: List[Dict[str, Any]] = []

        # 3) 写明细 + 扣减
        for (wh_id, item_id, code), qty in agg.items():
            line = OutboundLineV2(
                commit_id=commit_id,
                warehouse_id=wh_id,
                item_id=item_id,
                batch_code=code,
                qty=qty,
                ledger_ref=ref,
                ledger_trace_id=trace_id,
                created_at=ts,
            )
            session.add(line)

            await self.stock_svc.adjust(
                session=session,
                item_id=item_id,
                warehouse_id=wh_id,
                delta=-qty,
                reason="OUTBOUND_V2_SHIP",
                ref=ref,
                ref_line=1,
                occurred_at=ts,
                batch_code=code,
                trace_id=trace_id,
            )

            total_qty += qty
            results.append(
                {
                    "warehouse_id": wh_id,
                    "item_id": item_id,
                    "batch_code": code,
                    "qty": qty,
                    "status": "OK",
                }
            )

        # 4) 更新头表 updated_at
        await session.execute(
            text(
                """
                UPDATE outbound_commits_v2
                   SET updated_at = :ts
                 WHERE id = :cid
                """
            ),
            {"ts": ts, "cid": commit_id},
        )

        # 5) 自动消费 soft reserve（best effort，不阻断主流程）
        try:
            await self._consume_reservations_for_trace(
                session=session,
                trace_id=trace_id,
            )
        except Exception:
            # 任何消费预占的错误，都不能影响出库本身
            pass

        return {
            "status": "OK",
            "commit_id": commit_id,
            "total_qty": total_qty,
            "idempotent": idempotent,
            "results": results,
        }
