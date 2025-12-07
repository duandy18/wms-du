from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.store_service import StoreService


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
        # 统一得到本次业务的 trace_id
        effective_trace_id = trace_id or ref

        # 使用 UTC-aware 时间，与数据库 timestamptz 列对齐
        created_at = datetime.now(timezone.utc)
        updated_at = created_at

        expire_dt: Optional[datetime] = None
        if expire_at is not None:
            expire_dt = created_at + timedelta(minutes=int(expire_at))

        # 1) 插入头表（若已存在则 DO NOTHING）
        insert_res_sql = text(
            """
            INSERT INTO reservations (
                platform, shop_id, warehouse_id, ref,
                status, created_at, updated_at, expire_at, trace_id
            )
            VALUES (
                :platform, :shop_id, :warehouse_id, :ref,
                'open', :created_at, :updated_at, :expire_at, :trace_id
            )
            ON CONFLICT (platform, shop_id, warehouse_id, ref)
            DO NOTHING
            RETURNING id
            """
        )
        key_params = {
            "platform": platform,
            "shop_id": shop_id,
            "warehouse_id": warehouse_id,
            "ref": ref,
            "created_at": created_at,
            "updated_at": updated_at,
            "expire_at": expire_dt,
            "trace_id": effective_trace_id,
        }
        inserted = await session.execute(insert_res_sql, key_params)
        reservation_id = inserted.scalar_one_or_none()

        # 2) 若插入失败，说明已有记录，查出 id 并更新 expire_at/updated_at/trace_id（只填空）
        if reservation_id is None:
            row = await session.execute(
                text(
                    """
                    SELECT id
                    FROM reservations
                    WHERE platform = :platform
                      AND shop_id = :shop_id
                      AND warehouse_id = :warehouse_id
                      AND ref = :ref
                    """
                ),
                {
                    "platform": platform,
                    "shop_id": shop_id,
                    "warehouse_id": warehouse_id,
                    "ref": ref,
                },
            )
            res = row.first()
            if res is None:
                # 理论上 ON CONFLICT DO NOTHING 后一定能查到；查不到只能视为严重并发问题
                raise RuntimeError(
                    "Failed to resolve reservation ID after concurrent insert conflict."
                )

            reservation_id = int(res[0])
            # 更新 expire_at（若给出）与 updated_at，并为旧记录补上 trace_id（仅在原值为 NULL 时）
            await session.execute(
                text(
                    """
                    UPDATE reservations
                       SET updated_at = :updated_at,
                           expire_at  = COALESCE(:expire_at, expire_at),
                           trace_id   = COALESCE(trace_id, :trace_id)
                     WHERE id = :rid
                    """
                ),
                {
                    "rid": reservation_id,
                    "updated_at": updated_at,
                    "expire_at": expire_dt,
                    "trace_id": effective_trace_id,
                },
            )

        # 3) reservation_lines 明细：按 ref_line UPSERT
        line_now = datetime.now(timezone.utc)

        update_line_sql = text(
            """
            UPDATE reservation_lines
               SET item_id    = :item,
                   qty        = :qty,
                   updated_at = :now
             WHERE reservation_id = :rid
               AND ref_line       = :ref_line
            """
        )
        insert_line_sql = text(
            """
            INSERT INTO reservation_lines (
                reservation_id, ref_line,
                item_id, qty, consumed_qty,
                created_at, updated_at
            )
            VALUES (
                :rid, :ref_line,
                :item, :qty, 0,
                :now, :now
            )
            """
        )

        for idx, ln in enumerate(lines or (), start=1):
            item_id = int(ln["item_id"])
            qty = int(ln["qty"])
            line_params = {
                "rid": reservation_id,
                "ref_line": idx,
                "item": item_id,
                "qty": qty,
                "now": line_now,
            }
            updated = await session.execute(update_line_sql, line_params)
            if updated.rowcount == 0:
                await session.execute(insert_line_sql, line_params)

        return {
            "status": "OK",
            "reservation_id": reservation_id,
        }

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
        res = await session.execute(
            text(
                """
                SELECT id, status
                  FROM reservations
                 WHERE platform = :platform
                   AND shop_id = :shop_id
                   AND warehouse_id = :warehouse_id
                   AND ref = :ref
                 LIMIT 1
                """
            ),
            {
                "platform": platform,
                "shop_id": shop_id,
                "warehouse_id": warehouse_id,
                "ref": ref,
            },
        )
        row = res.first()
        if row is None:
            return None
        return int(row[0]), str(row[1])

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
        res = await session.execute(
            text(
                """
                SELECT item_id, qty
                  FROM reservation_lines
                 WHERE reservation_id = :rid
                 ORDER BY ref_line ASC
                """
            ),
            {"rid": reservation_id},
        )
        return [(int(r[0]), int(r[1])) for r in res.fetchall()]

    # ------------------------------------------------------------------
    # 状态迁移：mark_consumed / mark_released
    # ------------------------------------------------------------------
    async def mark_consumed(self, session: AsyncSession, reservation_id: int) -> None:
        """
        将一张 reservation 标记为 consumed，并同步行的 consumed_qty。
        """
        now = datetime.now(timezone.utc)

        await session.execute(
            text(
                """
                UPDATE reservation_lines
                   SET consumed_qty = qty,
                       updated_at   = :now
                 WHERE reservation_id = :rid
                """
            ),
            {"rid": reservation_id, "now": now},
        )

        await session.execute(
            text(
                """
                UPDATE reservations
                   SET status    = 'consumed',
                       updated_at = :now
                 WHERE id = :rid
                """
            ),
            {"rid": reservation_id, "now": now},
        )

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
        now = datetime.now(timezone.utc)
        await session.execute(
            text(
                """
                UPDATE reservations
                   SET status     = :reason,
                       updated_at = :now
                 WHERE id = :rid
                """
            ),
            {"rid": reservation_id, "reason": reason, "now": now},
        )

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

        条件：
          - status = 'open'
          - expire_at IS NOT NULL
          - expire_at < now
        """
        now = now or datetime.now(timezone.utc)
        res = await session.execute(
            text(
                """
                SELECT id
                  FROM reservations
                 WHERE status = 'open'
                   AND expire_at IS NOT NULL
                   AND expire_at < :now
                 ORDER BY expire_at ASC, id ASC
                 LIMIT :limit
                """
            ),
            {"now": now, "limit": limit},
        )
        return [int(r[0]) for r in res.fetchall()]

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
        # 1) 决定使用哪个 warehouse_id
        wh_id: Optional[int] = warehouse_id
        if wh_id is None:
            # 尝试根据店铺默认仓解析
            wh_id = await StoreService.resolve_default_warehouse_for_platform_shop(
                session,
                platform=platform,
                shop_id=shop_id,
            )

        if wh_id is None:
            raise ReservationError(f"No warehouse specified or configured for {platform}/{shop_id}")

        # 2) 构造 plan（不访问 DB，不落库）
        plan: List[Dict[str, Any]] = []
        for ln in lines or []:
            item_id = int(ln["item_id"])
            qty = int(ln["qty"])
            plan.append(
                {
                    "warehouse_id": wh_id,
                    "item_id": item_id,
                    "qty": qty,
                    "batch_id": None,
                }
            )

        return {
            "status": "OK",
            "warehouse_id": wh_id,
            "plan": plan,
        }
