# app/services/stock_service.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Union

from fastapi import HTTPException
from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem
from app.models.enums import MovementType
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

    async def _requires_batch(self, session: AsyncSession, *, item_id: int) -> bool:
        row = await session.execute(
            SA("SELECT expiry_policy FROM items WHERE id=:i LIMIT 1"),
            {"i": int(item_id)},
        )
        v = row.scalar_one_or_none()
        return str(v or "").upper() == "REQUIRED"

    async def _ensure_supplier_lot_id(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        lot_code: str,
    ) -> int:
        code = str(lot_code).strip()
        if not code:
            raise ValueError("batch_code REQUIRED")

        row = await session.execute(
            SA(
                """
                INSERT INTO lots(
                    warehouse_id,
                    item_id,
                    lot_code_source,
                    lot_code,
                    source_receipt_id,
                    source_line_no,
                    -- required snapshots (NOT NULL)
                    item_lot_source_policy_snapshot,
                    item_expiry_policy_snapshot,
                    item_derivation_allowed_snapshot,
                    item_uom_governance_enabled_snapshot,
                    -- optional snapshots (nullable)
                    item_shelf_life_value_snapshot,
                    item_shelf_life_unit_snapshot
                )
                SELECT
                    :w,
                    :i,
                    'SUPPLIER',
                    :code,
                    NULL,
                    NULL,
                    it.lot_source_policy,
                    it.expiry_policy,
                    it.derivation_allowed,
                    it.uom_governance_enabled,
                    it.shelf_life_value,
                    it.shelf_life_unit
                  FROM items it
                 WHERE it.id = :i
                ON CONFLICT (warehouse_id, item_id, lot_code)
                WHERE lot_code IS NOT NULL
                DO NOTHING
                RETURNING id
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "code": code},
        )
        got = row.scalar_one_or_none()
        if got is not None:
            return int(got)

        row2 = await session.execute(
            SA(
                """
                SELECT id
                  FROM lots
                 WHERE warehouse_id = :w
                   AND item_id = :i
                   AND lot_code_source = 'SUPPLIER'
                   AND lot_code = :code
                 LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "code": code},
        )
        got2 = row2.scalar_one_or_none()
        if got2 is None:
            raise ValueError("lot_not_found")
        return int(got2)

    async def _ensure_internal_lot_id(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        ref: str,
        occurred_at: Optional[datetime],
    ) -> int:
        """
        Lot-only world（终态）：
        - 即使是非批次商品，也必须落在一个确定的 lot_id 上。
        - “无批次”不再用 lot_id=NULL 表达，而是 INTERNAL lot（lots.lot_code 为 NULL）表达。
        """
        # 1) reuse existing INTERNAL + lot_code IS NULL
        row = await session.execute(
            SA(
                """
                SELECT id
                  FROM lots
                 WHERE warehouse_id = :w
                   AND item_id      = :i
                   AND lot_code_source = 'INTERNAL'
                   AND lot_code IS NULL
                 ORDER BY id ASC
                 LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id)},
        )
        got = row.scalar_one_or_none()
        if got is not None:
            return int(got)

        # 2) create (or reuse) a synthetic inbound_receipt as INTERNAL lot source
        # inbound_receipts.ref is unique; use deterministic ref so repeated calls are stable
        ts = occurred_at or datetime.now(UTC)
        src_ref = f"SYS:INTERNAL_LOT:{int(warehouse_id)}:{int(item_id)}"
        r = await session.execute(
            SA(
                """
                INSERT INTO inbound_receipts (
                  warehouse_id,
                  source_type,
                  source_id,
                  ref,
                  trace_id,
                  status,
                  remark,
                  occurred_at
                )
                VALUES (
                  :wh,
                  'PO',
                  NULL,
                  :ref,
                  NULL,
                  'DRAFT',
                  'SYS internal lot source receipt',
                  :ts
                )
                ON CONFLICT (ref) DO UPDATE SET updated_at = now()
                RETURNING id
                """
            ),
            {"wh": int(warehouse_id), "ref": str(src_ref), "ts": ts},
        )
        receipt_id = int(r.scalar_one())

        # 3) insert INTERNAL lot (must satisfy DB check: source_receipt_id/source_line_no NOT NULL)
        r2 = await session.execute(
            SA(
                """
                INSERT INTO lots (
                  warehouse_id,
                  item_id,
                  lot_code_source,
                  lot_code,
                  source_receipt_id,
                  source_line_no,
                  created_at,
                  item_shelf_life_value_snapshot,
                  item_shelf_life_unit_snapshot,
                  item_lot_source_policy_snapshot,
                  item_expiry_policy_snapshot,
                  item_derivation_allowed_snapshot,
                  item_uom_governance_enabled_snapshot
                )
                SELECT
                  :wh,
                  it.id,
                  'INTERNAL',
                  NULL,
                  :rid,
                  1,
                  now(),
                  it.shelf_life_value,
                  it.shelf_life_unit,
                  it.lot_source_policy,
                  it.expiry_policy,
                  it.derivation_allowed,
                  it.uom_governance_enabled
                FROM items it
                WHERE it.id = :i
                ON CONFLICT DO NOTHING
                RETURNING id
                """
            ),
            {"wh": int(warehouse_id), "i": int(item_id), "rid": int(receipt_id)},
        )
        lot_id = r2.scalar_one_or_none()
        if lot_id is not None:
            return int(lot_id)

        # 4) fallback: select the inserted lot
        r3 = await session.execute(
            SA(
                """
                SELECT id
                  FROM lots
                 WHERE warehouse_id = :wh
                   AND item_id = :i
                   AND lot_code_source = 'INTERNAL'
                   AND source_receipt_id = :rid
                   AND source_line_no = 1
                 LIMIT 1
                """
            ),
            {"wh": int(warehouse_id), "i": int(item_id), "rid": int(receipt_id)},
        )
        got3 = r3.scalar_one_or_none()
        if got3 is None:
            raise ValueError("failed to ensure INTERNAL lot")
        return int(got3)

    async def _load_on_hand_qty(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        batch_code: Optional[str],
    ) -> int:
        row = (
            await session.execute(
                SA(
                    """
                    SELECT COALESCE(SUM(s.qty), 0) AS qty
                      FROM stocks_lot s
                      LEFT JOIN lots lo ON lo.id = s.lot_id
                     WHERE s.warehouse_id = :w
                       AND s.item_id      = :i
                       AND lo.lot_code IS NOT DISTINCT FROM CAST(:c AS TEXT)
                    """
                ),
                {"w": int(warehouse_id), "i": int(item_id), "c": batch_code},
            )
        ).first()
        if not row:
            return 0
        try:
            return int(row[0] or 0)
        except Exception:
            return 0

    def _classify_adjust_value_error(self, msg: str) -> str:
        m = (msg or "").strip()

        if "insufficient stock" in m.lower():
            return "insufficient_stock"

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
            bc_norm = (str(batch_code).strip() if batch_code is not None else None) or None

            if bc_norm is None:
                if await self._requires_batch(session, item_id=int(item_id)):
                    raise ValueError("batch_code REQUIRED")
                # ✅ 终态：非批次商品也必须有 lot_id（INTERNAL lot，lot_code 可为 NULL）
                resolved_lot_id = lot_id or await self._ensure_internal_lot_id(
                    session,
                    warehouse_id=int(warehouse_id),
                    item_id=int(item_id),
                    ref=str(ref),
                    occurred_at=occurred_at,
                )
            else:
                resolved_lot_id = lot_id or await self._ensure_supplier_lot_id(
                    session,
                    warehouse_id=int(warehouse_id),
                    item_id=int(item_id),
                    lot_code=bc_norm,
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

            if kind == "insufficient_stock":
                if int(delta) < 0:
                    on_hand = await self._load_on_hand_qty(
                        session,
                        warehouse_id=int(warehouse_id),
                        item_id=int(item_id),
                        batch_code=bc_norm2,
                    )
                    required_qty = int(-int(delta))
                    short_qty = max(0, int(required_qty) - int(on_hand))
                else:
                    on_hand = await self._load_on_hand_qty(
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
