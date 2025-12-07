# app/services/reservation_consumer.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .reservation_service import ReservationService
from .stock_service import StockService


class ReservationConsumer:
    """
    Reservation 消费编排器（不管事务，只管业务）：

    - 状态相关：
        * 使用 ReservationService 获取 / 检查 reservation 头表
        * 获取 reservation_lines 明细
        * 标记 consumed（含行的 consumed_qty）
        * 标记 TTL 过期（release_expired_by_id）

    - 库存相关（v2 之后的策略）：
        * 不再直接 UPDATE stocks 或 INSERT stock_ledger
        * 出库扣减统一由 PickService / ShipService / OutboundService 负责
        * Soft Reserve 只记录“承诺”和“消耗”状态，不再动实仓

    Phase 3.6：曾经在 pick_consume 中调用 StockService.adjust 扣减库存，reason=SOFT_SHIP。
    当前版本起，该逻辑已经移除，避免“预占消费=发货”的歧义，库存只由真实出库动作负责。
    """

    def __init__(self, reservation_svc: ReservationService) -> None:
        self._reservation = reservation_svc
        # 目前保留 stock_svc 属性，仅为未来可能的扩展预留；当前版本不再使用
        self._stock = StockService()

    async def pick_consume(
        self,
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        ref: str,
        occurred_at,  # 当前版本仅用于日志/审计扩展预留
        trace_id: Optional[str] = None,
    ) -> Dict[str, object]:
        """
        对一张 reservation 执行“消费”操作（不包含事务和 advisory_lock）。

        v2 语义（新的硬口径）：

        - Soft Reserve 只负责“承诺”和“消耗”：
            * reservations / reservation_lines 记录 qty / consumed_qty / status
            * 不再扣减 stocks、不再写 stock_ledger
        - 真实扣库：
            * 统一由 PickService / ShipService / OutboundService 等显式出库动作完成
            * 这些动作会写出 PICK / SHIP 等台账

        行为：

        - 无 reservation：
            * 返回 status='NOOP'
            * 不动任何状态、库存

        - 已为 consumed：
            * 返回 status='NOOP'
            * 不重复标记

        - 首次消费：
            * 对 reservation 下所有行，全额消费：
                - ReservationService.mark_consumed 负责：
                    + consumed_qty = qty
                    + reservations.status = 'consumed'
            * 返回 status='CONSUMED'

        trace_id 目前仅向上层透出，在本方法中不再写入 ledger。
        """

        # 1) 基于业务键找到 reservation
        key_params = {
            "platform": platform,
            "shop_id": shop_id,
            "warehouse_id": warehouse_id,
            "ref": ref,
        }
        r = await self._reservation.get_by_key(session, **key_params)
        if r is None:
            # PICK / SHIP 先到，RESERVE 未到 → NOOP
            return {
                "status": "NOOP",
                "reservation_id": None,
            }

        reservation_id, status = r

        # 已经 consumed：并发重放 → NOOP
        if status == "consumed":
            return {
                "status": "NOOP",
                "reservation_id": reservation_id,
            }

        # 2) 取出当前行，确认确实有东西可消费
        line_rows: List[Tuple[int, int]] = await self._reservation.get_lines(
            session, reservation_id
        )
        if not line_rows:
            # 没有明细，视为 NOOP，并把单标记为 consumed 避免死循环
            await self._reservation.mark_consumed(session, reservation_id)
            return {
                "status": "NOOP",
                "reservation_id": reservation_id,
            }

        # 3) 只做状态迁移：标记为 consumed（行的 consumed_qty 由 ReservationService 负责）
        await self._reservation.mark_consumed(session, reservation_id)

        return {
            "status": "CONSUMED",
            "reservation_id": reservation_id,
        }

    async def release_expired_by_id(
        self,
        session: AsyncSession,
        reservation_id: int,
        *,
        reason: str = "expired",
        trace_id: Optional[str] = None,  # 预留：目前不使用
    ) -> Dict[str, object]:
        """
        TTL 回收场景：按 reservation_id 将一张 open 单标记为 expired。

        语义：
          - 若该 id 不存在 → status='NOOP', reservation_id=None
          - 若该单 status != 'open' → status='NOOP', reservation_id=原 id
          - 若该单 status='open'：
              * 使用 ReservationService.mark_released 写入：
                  - reservations.status = reason（默认 'expired'）
                  - released_at = now(), updated_at = now()
              * 不动 reservation_lines
              * 不动 stocks / stock_ledger
              * 返回 status='EXPIRED'

        并发 & 幂等：
          - 上层应在事务 + advisory lock 内调用；
          - 多个并发路径对同一 id 调用时，只有第一次能看到 status='open'；
          - 之后重放会走到 status!='open' 分支，视为 NOOP。
        """

        res = await session.execute(
            text(
                """
                SELECT status
                  FROM reservations
                 WHERE id = :rid
                 FOR UPDATE
                """
            ),
            {"rid": reservation_id},
        )
        row = res.first()
        if row is None:
            return {
                "status": "NOOP",
                "reservation_id": None,
            }

        current_status = str(row[0])

        if current_status != "open":
            return {
                "status": "NOOP",
                "reservation_id": reservation_id,
            }

        await self._reservation.mark_released(
            session,
            reservation_id=reservation_id,
            reason=reason,
        )

        return {
            "status": "EXPIRED",
            "reservation_id": reservation_id,
        }
