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
NOEXP_BATCH_CODE = "NOEXP"


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
                    SELECT id, has_shelf_life, shelf_life_value, shelf_life_unit
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
            return {"has_shelf_life": False, "shelf_life_value": None, "shelf_life_unit": None}

        return {
            "has_shelf_life": bool(row.get("has_shelf_life") or False),
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
        has_sl = bool(policy.get("has_shelf_life") or False)

        # batch_code
        code = str(batch_code).strip() if batch_code and str(batch_code).strip() else ""
        if not code:
            code = NOEXP_BATCH_CODE if not has_sl else f"AUTO-{iid}-1"

        # 日期规则
        if has_sl:
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
            # 无有效期：强制归 NOEXP（如果调用方传了别的 batch_code 也允许保留，但默认 NOEXP）
            if not (batch_code and str(batch_code).strip()):
                code = NOEXP_BATCH_CODE

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

        ins = await session.execute(
            sa.text(
                """
                INSERT INTO items (sku, name, uom)
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

        row2 = await session.execute(sa.text("SELECT id FROM items WHERE sku=:s LIMIT 1"), {"s": sku})
        return int(row2.scalar_one())
