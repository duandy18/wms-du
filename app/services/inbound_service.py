# app/services/inbound_service.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService
from app.services.utils.expiry_resolver import resolve_batch_dates_for_item

UTC = timezone.utc


class InboundService:
    """
    v2 入库服务（与扫描通路解耦的通用入库入口）：

    设计要点：
    - 不再作为 /scan 路由的入口使用；/scan 统一走 scan_orchestrator + handle_receive。
    - 本服务适用于：
        * 单据驱动的手工入库（例如 /inbound、RMA、调整单等）
        * 需要按 sku 自动建档的后台批量任务

    数据模型（当前版本）：
    - 库存粒度： (warehouse_id, item_id, batch_code)
    - 入库动作统一委托 StockService.adjust(reason=INBOUND)。

    日期/保质期策略：
    - 若显式提供 expiry_date → 直接使用；
    - 否则在有 production_date 且 Item 配置了 shelf_life 时，自动通过保质期推算 expiry_date；
    - 若两者均未提供，则默认 production_date = today，再按上述规则尝试推算；
    - 是否允许最终 expiry_date 为空由业务方控制（本服务不强制）。
    """

    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self.stock_svc = stock_svc or StockService()

    async def receive(
        self,
        session: AsyncSession,
        *,
        qty: int,
        ref: str,
        ref_line: int = 1,
        occurred_at: Optional[datetime] = None,
        # 主键维度（可缺省由本方法兜底/解析）
        warehouse_id: Optional[int] = None,
        batch_code: Optional[str] = None,
        # 二选一：优先 item_id；否则 sku
        item_id: Optional[int] = None,
        sku: Optional[str] = None,
        # 日期信息（v2 推荐提供其一；缺省时本方法用 today 兜底并结合保质期推算）
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
        # Trace 维度：用于写入 stock_ledger.trace_id（可选）
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        # ── 1) 基本校验 ─────────────────────────────────────────────────────
        if qty <= 0:
            raise ValueError("Receive quantity must be positive.")
        if item_id is None and (sku is None or not str(sku).strip()):
            raise ValueError("必须提供 item_id 或 sku（至少其一）。")

        # ── 2) sku → item_id 解析/创建 ─────────────────────────────────────
        iid = (
            int(item_id)
            if item_id is not None
            else await self._ensure_item_id(session, str(sku).strip())
        )

        # ── 3) 兜底缺省：warehouse / batch ────────────────────────────────
        wid = int(warehouse_id) if warehouse_id is not None else 1  # 基线默认仓
        code = str(batch_code).strip() if batch_code else f"AUTO-{iid}-1"

        # ── 4) 日期解析：结合 Item 保质期配置推算 expiry_date ─────────────
        # 若两者皆无，先默认生产日期为今天，再尝试按 shelf_life 推出到期日
        if production_date is None and expiry_date is None:
            production_date = date.today()

        production_date, expiry_date = await resolve_batch_dates_for_item(
            session,
            item_id=iid,
            production_date=production_date,
            expiry_date=expiry_date,
        )
        # 此处不强制 expiry_date 必须非空，允许“无保质期物料”入库；
        # 若某些仓库/品类必须强制，可在调用方做额外校验。

        # ── 5) 入库落账（委托 StockService.adjust） ───────────────────────
        res = await self.stock_svc.adjust(
            session=session,
            item_id=iid,
            warehouse_id=wid,
            delta=int(qty),
            reason=MovementType.INBOUND,
            ref=str(ref),
            ref_line=int(ref_line),
            occurred_at=occurred_at or datetime.now(UTC),
            batch_code=code,
            production_date=production_date,
            expiry_date=expiry_date,
            trace_id=trace_id,
        )

        return {
            "item_id": iid,
            "warehouse_id": wid,
            "batch_code": code,
            "qty": int(qty),
            "idempotent": bool(res.get("idempotent", False)),
            "applied": bool(res.get("applied", True)),
            "after": res.get("after"),
        }

    # ---------------- 内部：按 sku 解析/创建 item ----------------
    @staticmethod
    async def _ensure_item_id(session: AsyncSession, sku: str) -> int:
        """
        确保给定 sku 对应的 item_id 存在：
        - 若已存在则直接返回；
        - 若不存在则插入 items(sku, name=sku, unit='EA') 并返回新 id。
        """
        # 先查
        row = await session.execute(
            sa.text("SELECT id FROM items WHERE sku=:s LIMIT 1"), {"s": sku}
        )
        found = row.scalar_one_or_none()
        if found is not None:
            return int(found)

        # 不存在则按 sku upsert，新建时 name=sku, unit='EA'
        ins = await session.execute(
            sa.text(
                """
                INSERT INTO items (sku, name, unit)
                VALUES (:s, :n, 'EA')
                ON CONFLICT (sku) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """
            ),
            {"s": sku, "n": sku},
        )
        new_id = ins.scalar_one_or_none()
        if new_id is not None:
            return int(new_id)

        # 兜底：无 RETURNING 时再查一次
        row2 = await session.execute(
            sa.text("SELECT id FROM items WHERE sku=:s LIMIT 1"), {"s": sku}
        )
        return int(row2.scalar_one())
