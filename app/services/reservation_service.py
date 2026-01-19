from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.store_service import StoreService

from app.services.reservation_compat import reserve_plan_only
from app.services.reservation_persist import persist as _persist
from app.services.reservation_queries import find_expired as _find_expired
from app.services.reservation_queries import get_by_key as _get_by_key
from app.services.reservation_queries import get_lines as _get_lines
from app.services.reservation_state import mark_consumed as _mark_consumed
from app.services.reservation_state import mark_released as _mark_released


class ReservationError(Exception):
    """
    兼容层异常类型（legacy）：

    早期 Phase 2.x 测试中会从 reservation_service 导入 ReservationError。
    在 v2 结构中，我们不再主动抛出该异常，但为了兼容这些旧测试，
    保留该类型定义，以避免 ImportError。
    """

    pass


class ReservationService:
    """
    Reservation 状态机服务（v2 专业化版本）

    职责范围仅限：
      - reservations 头表
      - reservation_lines 明细表

    不负责：
      - stocks 库存
      - stock_ledger 台账

    重要约定：
      - 本服务自身不管理事务（不使用 session.begin()）
      - 调用方必须在外层开启事务（由 API / orchestrator 控制）

    Phase 3.7-A 补充：
      - persist 时统一写入 reservations.trace_id：
          * 若调用方传入 trace_id，则使用该值；
          * 若未传，则使用 ref 作为 trace_id；
      - 对已有记录的 UPDATE 会对 trace_id 进行“只填空不改值”的回填：
          * trace_id = COALESCE(trace_id, :trace_id)
    """

    # ------------------------------------------------------------------
    # 幂等建单 / 修改：persist
    # ------------------------------------------------------------------
    async def persist(
        self,
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        ref: str,
        lines: List[Dict[str, Any]],
        expire_at: Optional[int] = None,  # minutes
        trace_id: Optional[str] = None,  # Phase 3.7-A：链路主键
    ) -> Dict[str, Any]:
        """
        幂等建/改一张 reservation + 明细。

        语义：
          - 使用 (platform, shop_id, warehouse_id, ref) 作为业务键；
          - 若不存在，则 INSERT 一条 status='open' 的头记录；
          - 若已存在，则保持 status='open'，更新 expire_at（若传入）与 updated_at；
          - reservation_lines：
              * 按 ref_line=1..N 重新写入：
                  - 已有同 (reservation_id, ref_line) 则更新 item_id/qty；
                  - 没有则插入新行，consumed_qty 初始为 0；
              * 不会删除多余 ref_line。

        Phase 3.7-A：trace_id 规则
          - effective_trace_id = trace_id or ref
          - 新插入的头记录总会写入 trace_id = effective_trace_id；
          - 对已存在记录，在 UPDATE 阶段执行：
              trace_id = COALESCE(trace_id, :trace_id)
            只为旧数据填补空值，不覆盖已有非空 trace_id。
        """
        return await _persist(
            session,
            platform=platform,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            ref=ref,
            lines=lines,
            expire_at=expire_at,
            trace_id=trace_id,
        )

    # ------------------------------------------------------------------
    # 查询：按业务键取头记录
    # ------------------------------------------------------------------
    async def get_by_key(
        self,
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        warehouse_id: int,
        ref: str,
    ) -> Optional[Tuple[int, str]]:
        """
        根据业务键获取 reservation 的 (id, status)。
        """
        return await _get_by_key(
            session,
            platform=platform,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            ref=ref,
        )

    # ------------------------------------------------------------------
    # 查询：取明细行 (item_id, qty)
    # ------------------------------------------------------------------
    async def get_lines(
        self,
        session: AsyncSession,
        reservation_id: int,
    ) -> List[Tuple[int, int]]:
        """
        获取某张 reservation 的明细行 (item_id, qty) 列表。
        """
        return await _get_lines(session, reservation_id)

    # ------------------------------------------------------------------
    # 状态迁移：mark_consumed / mark_released
    # ------------------------------------------------------------------
    async def mark_consumed(self, session: AsyncSession, reservation_id: int) -> None:
        """
        将一张 reservation 标记为 consumed，并同步行的 consumed_qty。
        """
        await _mark_consumed(session, reservation_id)

    async def mark_released(
        self,
        session: AsyncSession,
        reservation_id: int,
        *,
        reason: str = "expired",
    ) -> None:
        """
        将一张 reservation 标记为“释放/过期”等终结状态。
        """
        await _mark_released(session, reservation_id, reason=reason)

    # ------------------------------------------------------------------
    # TTL 辅助：find_expired
    # ------------------------------------------------------------------
    async def find_expired(
        self,
        session: AsyncSession,
        *,
        now: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[int]:
        """
        查找已过期但仍为 open 的 reservation.id 列表，用于 TTL worker。
        """
        return await _find_expired(session, now=now, limit=limit)

    # ------------------------------------------------------------------
    # 兼容层：纯计划版 reserve（不落账、不落库）
    # ------------------------------------------------------------------
    @staticmethod
    async def reserve(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        ref: str,
        lines: List[Dict[str, Any]],
        warehouse_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        兼容旧测试用的“纯计划版” Reserve：

        特征：
          - 只根据 store_warehouse 绑定和显式 warehouse_id 计算计划；
          - 不写 reservations / reservation_lines / stock_ledger；
          - 不扣库存；
          - 幂等（同样输入返回相同结果）；
          - 无默认仓且未传 warehouse_id 时抛 ReservationError。

        输出：
          {
            "status": "OK",
            "warehouse_id": <int>,
            "plan": [
              {"warehouse_id": wh, "item_id": ..., "qty": ..., "batch_id": None},
              ...
            ]
          }
        """
        # Route C 合同护栏：不允许默认仓/兜底推断。
        # 兼容层 reserve 只接受“显式 warehouse_id”。
        if warehouse_id is None:
            raise ReservationError("warehouse_id is required for reserve")

        _ = StoreService  # 保持与原文件一致的依赖语义（仅用于 resolve_default_warehouse）
        return await reserve_plan_only(
            session,
            platform=platform,
            shop_id=shop_id,
            ref=ref,
            lines=lines,
            warehouse_id=warehouse_id,
            reservation_error_type=ReservationError,
        )
