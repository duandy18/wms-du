# app/services/stock_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import DATABASE_URL
# ⚠️ 不再导入 app.models.Stock，当前实现不需要该模型

UTC = timezone.utc


class StockService:
    """
    设计要点：
    - 不缓存/共享 AsyncSession；所有写入都使用调用方传入的 session（每请求独立）。
    - 只读统计（SUM 等）使用一次性 NullPool 引擎+连接，用后立即 dispose，
      彻底规避 asyncpg “another operation is in progress / Future attached to a different loop”。
    """

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
        最小演示实现：直接调 stocks 表数量。
        你的项目如有 FEFO/批次/台账/触发器，请替换为原有写法，仅保留 _get_stocks_sum 的用法。
        """
        # 1) 确保存在库存行（根据你真实 schema 调整）
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

        # 2) 更新数量
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

        # 3) 读取 after 值（独立连接）
        after_qty = await self._get_stocks_sum(session=session, item_id=item_id, location_id=location_id)

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
        简化的两腿移库（putaway）；保序 await，避免并发。
        """
        await self.adjust(
            session=session,
            item_id=item_id,
            location_id=from_location_id,
            delta=-abs(int(qty)),
            reason="PUTAWAY",
            ref=scan_ref,
        )
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
        盘点：实际数 - 帐面数 = 差额，做一次性调整。
        """
        # 确保上文写入可见
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
    # 关键：只读统计走独立一次性连接
    # -------------------------
    async def _get_stocks_sum(self, *, session: AsyncSession, item_id: int, location_id: int) -> int:
        """
        - 先 flush 当前 Session，保证读到本事务内最新变更；
        - 用 NullPool 引擎获取一次性连接做 SELECT；
        - 用完 dispose，杜绝跨事件循环复用。
        """
        try:
            await session.flush()
        except Exception:
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
                return int(row.scalar_one() or 0)
        finally:
            await tmp_engine.dispose()
