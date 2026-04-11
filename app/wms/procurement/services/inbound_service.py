# app/wms/procurement/services/inbound_service.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.wms.stock.services.stock_service import StockService
from app.wms.shared.services.expiry_resolver import normalize_batch_dates_for_item

UTC = timezone.utc


class InboundService:
    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self.stock_svc = stock_svc or StockService()

    @staticmethod
    async def _load_item_policy(session: AsyncSession, item_id: int) -> dict[str, object]:
        row = (
            (
                await session.execute(
                    sa.text(
                        """
                    SELECT id, expiry_policy, shelf_life_value, shelf_life_unit
                      FROM items
                     WHERE id = :id
                     LIMIT 1
                    """
                    ),
                    {"id": int(item_id)},
                )
            )
            .mappings()
            .first()
        )

        if not row:
            return {"expiry_policy": "NONE", "shelf_life_value": None, "shelf_life_unit": None}

        return {
            "expiry_policy": str(row.get("expiry_policy")),
            "shelf_life_value": row.get("shelf_life_value"),
            "shelf_life_unit": row.get("shelf_life_unit"),
        }

    async def receive(
        self,
        session: AsyncSession,
        *,
        qty: int,
        ref: str,
        ref_line: int = 1,
        occurred_at: Optional[datetime] = None,
        warehouse_id: Optional[int] = None,
        batch_code: Optional[str] = None,
        item_id: Optional[int] = None,
        sku: Optional[str] = None,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
        trace_id: Optional[str] = None,
        sub_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        入库服务（owner 入口）：

        - REQUIRED/NONE 的批次裁决仍由 StockService.adjust(合同闸门)负责；
        - 但对 expiry_policy=NONE 的商品，入口层必须把 batch_code 投影为 None，
          否则会触发合同的 batch_forbidden（这符合终态合同：NONE 商品 batch_code 必须为 null）；
        - 对 REQUIRED 商品，入口层必须先把用户输入归一为 resolved_production_date /
          resolved_expiry_date，再交给 lot / ledger 写入口。
        """
        if qty <= 0:
            raise ValueError("Receive quantity must be positive.")
        if item_id is None and (sku is None or not str(sku).strip()):
            raise ValueError("必须提供 item_id 或 sku（至少其一）。")

        iid = int(item_id) if item_id is not None else await self._ensure_item_id(session, str(sku).strip())
        wid = int(warehouse_id) if warehouse_id is not None else 1

        policy = await self._load_item_policy(session, iid)
        expiry_policy = str(policy.get("expiry_policy") or "").upper()
        requires_batch = expiry_policy == "REQUIRED"

        # 轻量归一：空串/空格 -> None
        code = (str(batch_code).strip() if batch_code is not None else None) or None

        # NONE 商品必须把 batch_code 投影为 None（不允许传入任何值）
        if not requires_batch:
            code = None
            resolved_production_date = None
            resolved_expiry_date = None
        else:
            if production_date is None and expiry_date is None:
                raise ValueError("该商品需要有效期管理：必须提供生产日期或到期日期（至少其一）")

            resolved_production_date, resolved_expiry_date, _resolution_mode = await normalize_batch_dates_for_item(
                session,
                item_id=iid,
                production_date=production_date,
                expiry_date=expiry_date,
            )

            if resolved_production_date is None:
                raise ValueError("批次受控商品必须提供 production_date，或提供可结合保质期反推出 production_date 的 expiry_date。")

            if resolved_expiry_date is None:
                raise ValueError("未提供到期日期，且商品未配置可用于推算的保质期，无法形成 canonical expiry_date。")

        meta = {"sub_reason": sub_reason} if (sub_reason and str(sub_reason).strip()) else None

        res = await self.stock_svc.adjust(
            session=session,
            item_id=iid,
            warehouse_id=wid,
            delta=int(qty),
            reason=MovementType.INBOUND,
            ref=str(ref),
            ref_line=int(ref_line),
            occurred_at=occurred_at or datetime.now(UTC),
            meta=meta,
            batch_code=code,
            production_date=resolved_production_date,
            expiry_date=resolved_expiry_date,
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

    @staticmethod
    async def _ensure_item_id(session: AsyncSession, sku: str) -> int:
        row = await session.execute(sa.text("SELECT id FROM items WHERE sku=:s LIMIT 1"), {"s": sku})
        found = row.scalar_one_or_none()
        if found is not None:
            return int(found)

        ins = await session.execute(
            sa.text(
                """
                INSERT INTO items (
                    sku,
                    name,
                    lot_source_policy,
                    expiry_policy,
                    derivation_allowed,
                    uom_governance_enabled
                )
                VALUES (
                    :s,
                    :n,
                    'SUPPLIER_ONLY',
                    'NONE',
                    true,
                    false
                )
                ON CONFLICT (sku) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """
            ),
            {"s": sku, "n": sku},
        )
        new_id = ins.scalar_one_or_none()
        if new_id is not None:
            return int(new_id)

        row2 = await session.execute(sa.text("SELECT id FROM items WHERE sku=:s LIMIT 1"), {"s": sku})
        return int(row2.scalar_one())
