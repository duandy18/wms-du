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

        # expiry_policy 是 enum，可能返回 str/Enum-like；统一转 str
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
        # ✅ 合同化：业务细分（采购入库/退货入库/杂项入库等）
        sub_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        if qty <= 0:
            raise ValueError("Receive quantity must be positive.")
        if item_id is None and (sku is None or not str(sku).strip()):
            raise ValueError("必须提供 item_id 或 sku（至少其一）。")

        iid = (
            int(item_id)
            if item_id is not None
            else await self._ensure_item_id(session, str(sku).strip())
        )
        wid = int(warehouse_id) if warehouse_id is not None else 1

        policy = await self._load_item_policy(session, iid)
        expiry_policy = str(policy.get("expiry_policy") or "").upper()
        requires_batch = expiry_policy == "REQUIRED"

        # Phase L：不再默认填充 NOEXP/AUTO 批次码。
        # - REQUIRED（有效期管理商品）：必须显式提供 batch_code（供应商批次码）
        # - NONE（无有效期/无批次商品）：必须 batch_code=None（展示码为空）
        code = (str(batch_code).strip() if batch_code is not None else "") or None

        # 日期规则
        if requires_batch:
            if code is None:
                raise ValueError("该商品需要有效期管理：必须提供 batch_code（供应商批次码）")
            if production_date is None:
                raise ValueError("该商品需要有效期管理：必须提供生产日期")

            # expiry_date 可缺省：尝试用参数推算
            prod, exp = await resolve_batch_dates_for_item(
                session,
                item_id=iid,
                production_date=production_date,
                expiry_date=expiry_date,
            )
            production_date, expiry_date = prod, exp

            if expiry_date is None:
                # 参数缺失导致推算失败
                raise ValueError("未提供到期日期，且商品未配置保质期参数，无法推算到期日期")
        else:
            production_date = None
            expiry_date = None
            # 无有效期商品：batch_code 必须为空（不再强制 NOEXP）
            code = None

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

    @staticmethod
    async def _ensure_item_id(session: AsyncSession, sku: str) -> int:
        row = await session.execute(sa.text("SELECT id FROM items WHERE sku=:s LIMIT 1"), {"s": sku})
        found = row.scalar_one_or_none()
        if found is not None:
            return int(found)

        # Phase M-5: items.uom 已移除；必须补齐 items 的 NOT NULL 策略字段
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
