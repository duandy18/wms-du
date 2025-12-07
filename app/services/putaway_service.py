# app/services/putaway_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService


class SameLocationError(ValueError):
    """Putaway 左右库位相同的业务错误。"""

    def __init__(self, location_id: int) -> None:
        super().__init__(f"from_location_id 和 to_location_id 不能相同：{location_id}")
        self.location_id = location_id


class PutawayService:
    """
    Putaway 业务服务（v2 版）

    重要约定（结合当前 HEAD）：

    - StockService.adjust 仅按 (warehouse_id, item_id, batch_code) 维度调整库存 + 写台账；
      不再接受 location_id 参数。
    - 但作业层仍保留“库位”概念，因此：
        * 通过 locations 表反查 from_location_id / to_location_id 对应的 warehouse_id；
        * 要求两者 warehouse_id 一致（同一仓内移库）；
        * adjust 只动仓维度库存，location 颗粒度由上层视图 / 辅助工具解释。
    - 审计契约：
        * 左腿（源位扣减，delta < 0）：必须有 batch_code；
        * 右腿（目标位入库，delta > 0）：必须有 batch_code，
          且 production_date / expiry_date 至少提供一个。
    """

    def __init__(self, stock: Optional[StockService] = None) -> None:
        self.stock = stock or StockService()

    # ------------------------------------------------------------------ #
    # 内部工具：根据 location_id 解析 warehouse_id
    # ------------------------------------------------------------------ #
    @staticmethod
    async def _resolve_warehouse_for_location(
        session: AsyncSession,
        location_id: int,
    ) -> int:
        row = await session.execute(
            text(
                """
                SELECT warehouse_id
                  FROM locations
                 WHERE id = :loc_id
                """
            ),
            {"loc_id": location_id},
        )
        wh_id = row.scalar()
        if wh_id is None:
            raise ValueError(f"location_id={location_id} 不存在或未绑定仓库")
        return int(wh_id)

    # ------------------------------------------------------------------ #
    # 核心接口：putaway
    # ------------------------------------------------------------------ #
    async def putaway(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        from_location_id: int,
        to_location_id: int,
        qty: int,
        ref: str,
        batch_code: str,
        production_date: Optional[datetime] = None,
        expiry_date: Optional[datetime] = None,
        left_ref_line: int = 1,
    ) -> Dict[str, Any]:
        """
        SRC → DST 搬运 qty 件，保持台账 + 库存在 v2 世界观下自洽。

        - qty > 0
        - from_location_id != to_location_id
        - batch_code 必填
        - production_date / expiry_date 至少一个非空（右腿要求）
        """
        if qty <= 0:
            raise ValueError("qty must be > 0")

        if from_location_id == to_location_id:
            raise SameLocationError(from_location_id)

        if not batch_code or not str(batch_code).strip():
            raise ValueError("putaway 操作必须提供 batch_code")

        if production_date is None and expiry_date is None:
            raise ValueError("putaway 操作必须提供 production_date 或 expiry_date 至少其一")

        # 解析两侧库位对应的仓库，要求在同一仓内移库
        from_wh = await self._resolve_warehouse_for_location(session, from_location_id)
        to_wh = await self._resolve_warehouse_for_location(session, to_location_id)

        if from_wh != to_wh:
            raise ValueError(
                f"跨仓 putaway 暂不支持：from_location_id={from_location_id} → to_location_id={to_location_id}，"
                f"warehouse_id 分别为 {from_wh} / {to_wh}"
            )

        now = datetime.now().astimezone()

        # 左腿：源位扣减（仓维度视角 → 同一仓出库）
        await self.stock.adjust(
            session=session,
            item_id=item_id,
            warehouse_id=from_wh,
            delta=-qty,
            reason=MovementType.PUTAWAY,
            ref=ref,
            ref_line=left_ref_line,
            occurred_at=now,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
        )

        # 右腿：目标位入库（同仓 +qty），ref_line = left_ref_line + 1
        await self.stock.adjust(
            session=session,
            item_id=item_id,
            warehouse_id=to_wh,
            delta=qty,
            reason=MovementType.PUTAWAY,
            ref=ref,
            ref_line=left_ref_line + 1,
            occurred_at=now,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
        )

        return {
            "status": "OK",
            "moved": qty,
            "from_location_id": from_location_id,
            "to_location_id": to_location_id,
            "warehouse_id": from_wh,
            "ref": ref,
            "left_ref_line": left_ref_line,
            "right_ref_line": left_ref_line + 1,
        }
