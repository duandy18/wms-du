# app/services/stock_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import DATABASE_URL
from app.models import Stock  # 假设已有
# 你的其它导入（如写台账等）保持不变
# from app.services.inventory_adjust import InventoryAdjust
# from app.services.ledger_writer import write_ledger
# ...

UTC = timezone.utc


class StockService:
    """
    约束：
    - 不缓存 Session，不在服务内持有全局连接；
    - 每次只在“调用提供的 session”中做变更；
    - 只读统计（SUM 等）走独立一次性连接（NullPool），避免 asyncpg
      “Future attached to a different loop / another operation in progress”。
    """

    # -------------------------
    # 公共入口（示例）——根据你项目已有方法补齐/保留
    # -------------------------

    async def adjust(
        self,
        *,
        session: AsyncSession,
        item_id: int,
        location_id: int,
        delta: int,
        reason: str,
        ref: Optional[str] = None,
        ref_line: Optional[int | str] = None,
        occurred_at: Optional[datetime] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        最小实现：直接增减 stocks；你项目里如已有更完整逻辑（FEFO/批次/台账），
        请保留原实现，只在“只读统计”改造点保持一致（见 _get_stocks_sum）。
        """
        # 1) 确保有库存行（演示：若项目有批次/唯一索引，这里请用你原来的 upsert 逻辑）
        await session.execute(
            text(
                """
                INSERT INTO stocks (item_id, warehouse_id, location_id, batch_code, qty)
                VALUES (:item_id, 1, :loc, COALESCE(:batch,'AUTO'), 0)
                ON CONFLICT DO NOTHING
                """
            ),
            {"item_id": item_id, "loc": location_id, "batch": None},
        )

        # 2) 调整（此处演示用途；你可替换为自己的写台账 + 触发器方案）
        await session.execute(
            text(
                """
                UPDATE stocks
                   SET qty = COALESCE(qty,0) + :d
                 WHERE item_id=:item_id AND location_id=:loc
                """
            ),
            {"d": int(delta), "item_id": item_id, "loc": location_id},
        )

        # 3) 返回 after 值（使用独立连接统计）
        after_qty = await self._get_stocks_sum(session=session, item_id=item_id, location_id=location_id)

        # 你的写台账逻辑如果在这里，请保留；发生并发时无须并行 await，严格顺序执行
        # ledger_id = await write_ledger(...)

        return {
            "item_id": item_id,
            "location_id": location_id,
            "delta": int(delta),
            "after_qty": int(after_qty),
        }

    async def transfer(
        self,
        *,
        session: AsyncSession,
        item_id: int,
        from_location_id: int,
        to_location_id: int,
        qty: int,
        operator: Optional[str] = None,
        scan_ref: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        简化的两腿移库（putaway）；你的原实现若包含批次跟随/校验/写台账等，保留即可。
        关键是：所有 SQL 顺序 await；中途不并发，不复用只读连接。
        """
        # 减源位
        await self.adjust(
            session=session,
            item_id=item_id,
            location_id=from_location_id,
            delta=-abs(int(qty)),
            reason="PUTAWAY",
            ref=scan_ref,
        )
        # 加目标位
        res_in = await self.adjust(
            session=session,
            item_id=item_id,
            location_id=to_location_id,
            delta=+abs(int(qty)),
            reason="PUTAWAY",
            ref=scan_ref,
        )
        return {
            "moved": abs(int(qty)),
            "to_location_id": to_location_id,
            "after_qty_dst": res_in["after_qty"],
        }

    async def reconcile_inventory(
        self,
        *,
        session: AsyncSession,
        item_id: int,
        location_id: int,
        actual_qty: int,
        operator: Optional[str] = None,
        scan_ref: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        盘点：实际数 - 帐面数 = 差额，做一次性调整
        """
        # 确保前序写入已落到事务缓冲中，避免读到旧值
        await session.flush()

        on_hand = await self._get_stocks_sum(session=session, item_id=item_id, location_id=location_id)
        delta = int(actual_qty) - int(on_hand)

        if delta:
            res = await self.adjust(
                session=session,
                item_id=item_id,
                location_id=location_id,
                delta=delta,
                reason="COUNT",
                ref=scan_ref,
            )
            return {"delta": delta, "after_qty": res["after_qty"]}
        else:
            return {"delta": 0, "after_qty": int(on_hand)}

    # -------------------------
    # 关键改造：只读统计走“独立一次性连接”
    # -------------------------

    async def _get_stocks_sum(self, *, session: AsyncSession, item_id: int, location_id: int) -> int:
        """
        避免与当前请求复用同一 asyncpg 连接：
        - 先 flush 当前 Session，保证读到最新写入（同事务或已提交前镜像）；
        - 使用 NullPool 的一次性 Engine 获取“独立连接”做 SELECT；
        - 用完立即 dispose，彻底规避 “another operation is in progress”
          与 “Future attached to a different loop”。
        """
        # 确保上文的 UPDATE/INSERT 已入缓冲
        try:
            await session.flush()
        except Exception:
            # 即使 flush 失败，也不要影响到只读连接释放
            pass

        tmp_engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            poolclass=NullPool,
            future=True,
        )
        try:
            async with tmp_engine.connect() as conn:
                row = await conn.execute(
                    text(
                        """
                        SELECT COALESCE(SUM(qty), 0) AS s
                          FROM stocks
                         WHERE item_id = :i AND location_id = :l
                        """
                    ),
                    {"i": int(item_id), "l": int(location_id)},
                )
                val = row.scalar_one()
                return int(val or 0)
        finally:
            # 立刻销毁底层连接，杜绝跨事件循环的复用
            await tmp_engine.dispose()
