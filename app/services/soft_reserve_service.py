from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .reservation_consumer import ReservationConsumer
from .reservation_service import ReservationService


class SoftReserveService:
    """
    Soft Reserve 门面服务（瘦身版）

    - delegating:
        * 预约头表/明细状态机 → ReservationService
        * 消费编排（扣库存 + 写台账） → ReservationConsumer

    - orchestration（仍保留在这里）:
        * 事务边界控制（_run_in_tx）
        * 并发控制（advisory lock）

    Phase 3.6：增加 trace_id 透传能力（当前自身不写 audit，只负责参数向下传递）。
    Phase 3.7-A：将 trace_id 作为全链路主键：
        * persist 时，保证 reservations.trace_id 被写入（trace_id or ref）
        * pick_consume / TTL 释放链路中，trace_id 继续向下传到 ReservationConsumer / StockService
    """

    def __init__(self) -> None:
        reservation_svc = ReservationService()
        self._reservation = reservation_svc
        self._consumer = ReservationConsumer(reservation_svc)

    # 小工具：在“已有事务”和“无事务”两种情况之间统一处理
    async def _run_in_tx(self, session: AsyncSession, fn):
        """
        如果 session 已经在事务中，则直接执行 fn；
        否则使用 async with session.begin() 包裹 fn。
        """
        if session.in_transaction():
            return await fn()
        async with session.begin():
            return await fn()

    # ----------------------------------------------------------------------
    # 1. 幂等建单：persist
    # ----------------------------------------------------------------------
    async def persist(
        self,
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        ref: str,
        lines: List[Dict[str, Any]],
        expire_at: Optional[int] = None,
        trace_id: Optional[str] = None,  # 上层可携带 trace_id
    ) -> Dict[str, Any]:
        """
        Phase 3.7-A：这里负责“决定”本次 reservation 的 trace_id：

        - 若上游已经传入 trace_id：全链使用该值；
        - 若上游未传：以 ref 作为 trace_id（保证该 reservation 能被 trace_id 聚合到）。
        """
        effective_trace_id = trace_id or ref

        async def _inner():
            return await self._reservation.persist(
                session,
                platform=platform,
                shop_id=shop_id,
                warehouse_id=warehouse_id,
                ref=ref,
                lines=lines,
                expire_at=expire_at,
                trace_id=effective_trace_id,  # 需要 ReservationService.persist 支持该参数
            )

        return await self._run_in_tx(session, _inner)

    # ----------------------------------------------------------------------
    # 2. 幂等消费：pick_consume
    # ----------------------------------------------------------------------
    async def pick_consume(
        self,
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        ref: str,
        occurred_at,
        trace_id: Optional[str] = None,  # 上层可携带 trace_id
    ) -> Dict[str, Any]:
        """
        Phase 3.7-A：
        - 继续把 trace_id 向下传递给 ReservationConsumer
        - ReservationConsumer 再传给 StockService.adjust，写入 stock_ledger.trace_id
        """

        async def _inner() -> Dict[str, Any]:
            # 1) 针对同一业务键加事务级 advisory lock
            await session.execute(
                text(
                    """
                    SELECT pg_advisory_xact_lock(
                        hashtext(:advisory_key)
                    )
                    """
                ),
                {
                    "advisory_key": f"{platform}:{shop_id}:{warehouse_id}:{ref}",
                },
            )

            # 2) 由 ReservationConsumer 完成具体消费逻辑（状态检查 + stocks + ledger）
            return await self._consumer.pick_consume(
                session,
                platform=platform,
                shop_id=shop_id,
                warehouse_id=warehouse_id,
                ref=ref,
                occurred_at=occurred_at,
                trace_id=trace_id,  # 继续透传
            )

        return await self._run_in_tx(session, _inner)

    # ----------------------------------------------------------------------
    # 3. 辅助接口：consume_reservation / release_reservation
    # ----------------------------------------------------------------------
    async def consume_reservation(
        self,
        session: AsyncSession,
        *,
        reservation_id: int,
        trace_id: Optional[str] = None,  # 预留
    ) -> Dict[str, Any]:
        async def _inner():
            await self._reservation.mark_consumed(session, reservation_id)
            return {
                "status": "OK",
                "reservation_id": reservation_id,
            }

        return await self._run_in_tx(session, _inner)

    async def release_reservation(
        self,
        session: AsyncSession,
        *,
        reservation_id: int,
        reason: str = "released",
        trace_id: Optional[str] = None,  # 预留：目前不落库，只是接口对齐
    ) -> Dict[str, Any]:
        """
        手工释放入口（例如后台管理界面手动点“释放”）：

        特征：
          - 不做 advisory lock；
          - 单纯标记状态，不区分 open/非 open；
          - 不动 stocks / ledger。

        TTL 自动过期请使用 release_expired_by_id。
        """

        async def _inner():
            await self._reservation.mark_released(session, reservation_id, reason=reason)
            return {
                "status": "OK",
                "reservation_id": reservation_id,
            }

        return await self._run_in_tx(session, _inner)

    # ----------------------------------------------------------------------
    # 4. TTL 支持：find_expired + release_expired_by_id
    # ----------------------------------------------------------------------
    async def find_expired(
        self,
        session: AsyncSession,
        *,
        now: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[int]:
        """
        TTL worker 使用的候选集扫描接口。

        行为：
          - 直接委托 ReservationService.find_expired
          - 不开启事务，不加锁（只读）
          - 并发安全由后续 release_expired_by_id 的
            事务 + advisory lock + FOR UPDATE 保证
        """
        return await self._reservation.find_expired(
            session,
            now=now,
            limit=limit,
        )

    async def release_expired_by_id(
        self,
        session: AsyncSession,
        *,
        reservation_id: int,
        reason: str = "expired",
        trace_id: Optional[str] = None,  # 上层可携带 trace_id（预留给后续链路观察）
    ) -> Dict[str, Any]:
        """
        TTL 回收入口：按 reservation_id 将一张 open 单标记为 expired。

        完整链路：
          1) 读出该 reservation 的业务键 (platform, shop_id, warehouse_id, ref)
          2) 基于该业务键申请事务级 advisory lock
          3) 调用 ReservationConsumer.release_expired_by_id 完成：
               - SELECT ... FOR UPDATE 检查 status
               - open -> expired 状态迁移（不动行、不动库存）

        要求：
          - 调用方不需要自行管理事务，统一走 _run_in_tx
          - 多 worker / 多进程重复调用是幂等的：
              * 首次看到 status='open' → EXPIRED
              * 之后 status!='open' → NOOP
        """

        async def _inner() -> Dict[str, Any]:
            # 1) 查出业务键（顺便检查是否存在）
            res = await session.execute(
                text(
                    """
                    SELECT platform, shop_id, warehouse_id, ref
                      FROM reservations
                     WHERE id = :rid
                    """
                ),
                {"rid": reservation_id},
            )
            row = res.first()
            if row is None:
                # TTL 扫描出来但已经被物理删除，视为 NOOP
                return {
                    "status": "NOOP",
                    "reservation_id": None,
                }

            # 注意：某些驱动返回 bytes，这里统一成 str
            platform, shop_id, warehouse_id, ref = [
                (v.decode() if isinstance(v, bytes) else v) for v in row
            ]

            # 2) 针对同一业务键加事务级 advisory lock
            await session.execute(
                text(
                    """
                    SELECT pg_advisory_xact_lock(
                        hashtext(:advisory_key)
                    )
                    """
                ),
                {
                    "advisory_key": f"{platform}:{shop_id}:{warehouse_id}:{ref}",
                },
            )

            # 3) 由 ReservationConsumer 完成具体 TTL 释放逻辑
            return await self._consumer.release_expired_by_id(
                session,
                reservation_id=reservation_id,
                reason=reason,
                trace_id=trace_id,  # 继续预留透传口（当前下游未使用）
            )

        return await self._run_in_tx(session, _inner)
