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
    v2 专业化库存内核（对外兼容 batch_code 入参，但内部以 lot-world 为主）：

    Phase 4C:
    - 新增 lot-world 主写入口 adjust_lot（写 stocks_lot + ledger(lot_id)）
    - ship_commit_direct 切到 lot-world

    Phase 4D:
    - 读口径（错误提示/可行动明细）统一以 stocks_lot 为准，禁止回读 legacy stocks。

    Phase 4E（本文件落地）：
    - StockService.adjust 对外签名保持不变；
    - 内部统一路由到 adjust_lot_impl（lot-world），禁止再走 legacy adjust_batch_impl。
    """

    async def _requires_batch(self, session: AsyncSession, *, item_id: int) -> bool:
        """
        Phase M 第一阶段：执行层禁止读取 items.has_shelf_life。

        批次受控唯一真相源：items.expiry_policy
        - expiry_policy='REQUIRED' => requires_batch=True
        - 其他（'NONE'/NULL）       => requires_batch=False
        """
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
        production_date: Optional[date],
        expiry_date: Optional[date],
    ) -> int:
        """
        Phase 4E：确保 SUPPLIER lot 存在，并返回 lot_id。
        - lots.lot_code_source='SUPPLIER'：lot_code 必须非空；source_receipt/source_line 必须为 NULL
        - expiry_date 可空；expiry_source 可空（DB 允许）

        注意：lots 表对策略快照（item_*_snapshot）有 NOT NULL 护栏，
        因此插入 lots 必须从 items 真相源读取并冻结快照字段。
        """
        code = str(lot_code).strip()
        if not code:
            raise ValueError("batch_code REQUIRED")  # 让上层分类为 batch_required

        # 生产日期：如果没给，沿用 CURRENT_DATE（保持与测试/seed 一致）
        prod = production_date or date.today()

        # expiry_source：仅当显式给 expiry_date 时标记为 EXPLICIT，否则置空
        expiry_source = "EXPLICIT" if expiry_date is not None else None

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
                    production_date,
                    expiry_date,
                    expiry_source,
                    -- required snapshots (NOT NULL)
                    item_lot_source_policy_snapshot,
                    item_expiry_policy_snapshot,
                    item_derivation_allowed_snapshot,
                    item_uom_governance_enabled_snapshot,
                    -- optional snapshots (nullable)
                    item_has_shelf_life_snapshot,
                    item_shelf_life_value_snapshot,
                    item_shelf_life_unit_snapshot,
                    item_uom_snapshot,
                    item_case_ratio_snapshot,
                    item_case_uom_snapshot
                )
                SELECT
                    :w,
                    :i,
                    'SUPPLIER',
                    :code,
                    NULL,
                    NULL,
                    :prod,
                    :exp,
                    :exp_src,
                    it.lot_source_policy,
                    it.expiry_policy,
                    it.derivation_allowed,
                    it.uom_governance_enabled,
                    it.has_shelf_life,
                    it.shelf_life_value,
                    it.shelf_life_unit,
                    it.uom,
                    it.case_ratio,
                    it.case_uom
                  FROM items it
                 WHERE it.id = :i
                ON CONFLICT (warehouse_id, item_id, lot_code_source, lot_code)
                WHERE lot_code_source = 'SUPPLIER'
                DO UPDATE SET
                    expiry_date = EXCLUDED.expiry_date
                RETURNING id
                """
            ),
            {
                "w": int(warehouse_id),
                "i": int(item_id),
                "code": code,
                "prod": prod,
                "exp": expiry_date,
                "exp_src": expiry_source,
            },
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

    async def _load_on_hand_qty(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        batch_code: Optional[str],
    ) -> int:
        """
        Phase 4D：
        - 只读 stocks_lot（lot-world 余额真相），用于错误提示/可行动明细；
        - 禁止读取 legacy stocks（避免口径回退，避免 rename/drop 时执行期炸裂）。

        batch_code 语义：
        - 在 lot-world 下作为展示码 lot_code（允许 NULL）
        - lot_id 为空时 LEFT JOIN lots 得到 lot_code=NULL，与 batch_code=NULL 精确匹配（IS NOT DISTINCT FROM）

        ✅ psycopg 对 NULL 参数类型推断敏感：显式 CAST(:c AS TEXT)
        """
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
        """
        Phase 4E：对外接口保持不变，但内部统一走 lot-world：
        - batch_code=None  => NULL lot 槽位（lot_id=None）
        - batch_code=str   => 确保 SUPPLIER lot 存在，得到 lot_id，再写入
        - 若商品批次受控（expiry_policy=REQUIRED）却 batch_code=None => 拒绝（422 batch_required）
        """
        try:
            bc_norm = (str(batch_code).strip() if batch_code is not None else None) or None

            # 1) 批次受控商品必须提供 batch_code（lot_code）
            if bc_norm is None:
                if await self._requires_batch(session, item_id=int(item_id)):
                    raise ValueError("batch_code REQUIRED")
                resolved_lot_id = lot_id  # 允许调用方显式传 lot_id（通常为 None）
            else:
                # 2) 对于展示码，确保 SUPPLIER lot 存在
                resolved_lot_id = lot_id or await self._ensure_supplier_lot_id(
                    session,
                    warehouse_id=int(warehouse_id),
                    item_id=int(item_id),
                    lot_code=bc_norm,
                    production_date=production_date,
                    expiry_date=expiry_date,
                )

            # 3) 统一走 lot-world 写入口
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
        # Phase 4C：切到 lot-world 实现
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
