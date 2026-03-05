# app/services/stock_service.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Union

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem
from app.models.enums import MovementType
from app.services.stock.lot_resolver import LotResolver
from app.services.stock_service_adjust import adjust_lot_impl
from app.services.stock_service_ship import ship_commit_direct_lot_impl

UTC = timezone.utc


class StockService:
    """
    v2 专业化库存内核（对外兼容 batch_code 入参，但内部以 lot-world 为主）。

    Phase M-5（结构治理：unit_governance 二阶段）：
    - lots 的单位快照列已移除（不再承载 base/purchase uom snapshot）
    - 单位真相源 = item_uoms；冻结点 = PO/Receipt lines 的 *_ratio_to_base_snapshot + qty_base
    """

    def __init__(self, lot_resolver: Optional[LotResolver] = None) -> None:
        self.lot_resolver = lot_resolver or LotResolver()

    def _classify_adjust_value_error(self, msg: str) -> str:
        m = (msg or "").strip()

        if "insufficient stock" in m.lower():
            return "insufficient_stock"
        if "item_not_found" in m.lower():
            return "item_not_found"
        if "lot_not_found" in m.lower():
            return "lot_not_found"
        if "lot_mismatch" in m.lower():
            return "lot_mismatch"

        if ("batch_code" in m.lower()) or ("批次" in m):
            if ("必须" in m) or ("required" in m.lower()):
                return "batch_required"
            return "stock_adjust_reject"

        return "stock_adjust_reject"

    async def adjust(  # noqa: C901
        self,
        session: AsyncSession,
        item_id: int,
        delta: int,
        reason: Union[str, MovementType],
        ref: str,
        ref_line: Optional[Union[int, str]] = None,
        occurred_at: Optional[datetime] = None,
        meta: Optional[Dict[str, Any]] = None,
        batch_code: Optional[str] = None,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
        *,
        warehouse_id: int,
        trace_id: Optional[str] = None,
        lot_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        try:
            requires_batch = await self.lot_resolver.requires_batch(session, item_id=int(item_id))
            bc_norm = (str(batch_code).strip() if batch_code is not None else None) or None

            # Phase 3：NONE/REQUIRED 入库合同收口（服务层硬化，禁止 NONE 带 batch_code）
            if (not requires_batch) and bc_norm is not None:
                raise ValueError("batch_code must be null for expiry-policy NONE items. Do not send batch_code.")

            if bc_norm is None:
                if requires_batch:
                    raise ValueError("batch_code REQUIRED")
                resolved_lot_id = lot_id or await self.lot_resolver.ensure_internal_lot_id(
                    session,
                    warehouse_id=int(warehouse_id),
                    item_id=int(item_id),
                    ref=str(ref),
                    occurred_at=occurred_at,
                )
            else:
                resolved_lot_id = lot_id or await self.lot_resolver.ensure_supplier_lot_id(
                    session,
                    warehouse_id=int(warehouse_id),
                    item_id=int(item_id),
                    lot_code=bc_norm,
                    occurred_at=occurred_at,
                )

            return await adjust_lot_impl(
                session=session,
                item_id=int(item_id),
                warehouse_id=int(warehouse_id),
                lot_id=resolved_lot_id,
                delta=int(delta),
                reason=reason,
                ref=str(ref),
                ref_line=ref_line,
                occurred_at=occurred_at,
                meta=meta,
                batch_code=bc_norm,
                production_date=production_date,
                expiry_date=expiry_date,
                trace_id=trace_id,
                utc_now=lambda: datetime.now(UTC),
                shadow_write_stocks=False,
            )
        except HTTPException:
            raise
        except ValueError as e:
            msg = str(e)
            kind = self._classify_adjust_value_error(msg)

            bc_norm2 = (str(batch_code).strip() if batch_code is not None else None) or None
            ctx = {
                "ref": str(ref),
                "ref_line": (str(ref_line) if ref_line is not None else None),
                "warehouse_id": int(warehouse_id),
                "item_id": int(item_id),
                "batch_code": bc_norm2,
                "delta": int(delta),
                "trace_id": trace_id,
                "lot_id": lot_id,
                "raw_error": msg,
            }

            if kind == "item_not_found":
                raise_problem(
                    status_code=422,
                    error_code="item_not_found",
                    message="商品不存在，写入被拒绝。",
                    context=ctx,
                    details=[{"type": "item", "path": "stock_adjust", "item_id": int(item_id), "reason": msg}],
                )

            if kind == "insufficient_stock":
                if int(delta) < 0:
                    on_hand = await self.lot_resolver.load_on_hand_qty(
                        session,
                        warehouse_id=int(warehouse_id),
                        item_id=int(item_id),
                        batch_code=bc_norm2,
                    )
                    required_qty = int(-int(delta))
                    short_qty = max(0, int(required_qty) - int(on_hand))
                else:
                    on_hand = await self.lot_resolver.load_on_hand_qty(
                        session,
                        warehouse_id=int(warehouse_id),
                        item_id=int(item_id),
                        batch_code=bc_norm2,
                    )
                    required_qty = int(delta)
                    short_qty = 0

                raise_problem(
                    status_code=409,
                    error_code="insufficient_stock",
                    message="库存不足，扣减失败。",
                    context=ctx,
                    details=[
                        {
                            "type": "shortage",
                            "path": "stock_adjust",
                            "item_id": int(item_id),
                            "batch_code": bc_norm2,
                            "required_qty": int(required_qty),
                            "available_qty": int(on_hand),
                            "short_qty": int(short_qty),
                            "reason": "insufficient_stock",
                        }
                    ],
                )

            if kind == "batch_required":
                raise_problem(
                    status_code=422,
                    error_code="batch_required",
                    message="批次受控商品必须提供批次。",
                    context=ctx,
                    details=[
                        {
                            "type": "batch",
                            "path": "stock_adjust",
                            "item_id": int(item_id),
                            "batch_code": bc_norm2,
                            "reason": msg,
                        }
                    ],
                )

            if kind == "lot_not_found":
                raise_problem(
                    status_code=404,
                    error_code="lot_not_found",
                    message="lot 不存在，写入被拒绝。",
                    context=ctx,
                    details=[
                        {
                            "type": "lot",
                            "path": "stock_adjust",
                            "warehouse_id": int(warehouse_id),
                            "item_id": int(item_id),
                            "lot_id": lot_id,
                            "reason": "lot_not_found",
                        }
                    ],
                )

            if kind == "lot_mismatch":
                raise_problem(
                    status_code=409,
                    error_code="lot_mismatch",
                    message="lot 与 warehouse/item 不匹配，写入被拒绝。",
                    context=ctx,
                    details=[
                        {
                            "type": "lot",
                            "path": "stock_adjust",
                            "warehouse_id": int(warehouse_id),
                            "item_id": int(item_id),
                            "lot_id": lot_id,
                            "reason": "lot_mismatch",
                        }
                    ],
                )

            raise_problem(
                status_code=422,
                error_code="stock_adjust_reject",
                message="库存调整请求不合法。",
                context=ctx,
                details=[{"type": "validation", "path": "stock_adjust", "reason": msg}],
            )

    async def adjust_lot(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        warehouse_id: int,
        lot_id: Optional[int],
        delta: int,
        reason: Union[str, MovementType],
        ref: str,
        ref_line: Optional[Union[int, str]] = None,
        occurred_at: Optional[datetime] = None,
        meta: Optional[Dict[str, Any]] = None,
        batch_code: Optional[str] = None,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
        trace_id: Optional[str] = None,
        shadow_write_stocks: bool = False,
    ) -> Dict[str, Any]:
        return await adjust_lot_impl(
            session=session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            lot_id=lot_id,
            delta=int(delta),
            reason=reason,
            ref=str(ref),
            ref_line=ref_line,
            occurred_at=occurred_at,
            meta=meta,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
            trace_id=trace_id,
            utc_now=lambda: datetime.now(UTC),
            shadow_write_stocks=bool(shadow_write_stocks),
        )

    async def ship_commit_direct(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        platform: str,
        shop_id: str,
        ref: str,
        lines: list[dict[str, int]],
        occurred_at: Optional[datetime] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await ship_commit_direct_lot_impl(
            session=session,
            warehouse_id=warehouse_id,
            platform=platform,
            shop_id=shop_id,
            ref=ref,
            lines=lines,
            occurred_at=occurred_at,
            trace_id=trace_id,
            utc_now=lambda: datetime.now(UTC),
            adjust_lot_fn=self.adjust_lot,
        )
