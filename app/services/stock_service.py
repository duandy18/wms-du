# app/services/stock_service.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Union

from fastapi import HTTPException
from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem
from app.models.enums import MovementType
from app.services.stock_service_adjust import adjust_impl
from app.services.stock_service_batches import ensure_batch_dict
from app.services.stock_service_ship import ship_commit_direct_impl

UTC = timezone.utc


class StockService:
    """
    v2 专业化库存内核（槽位维度批次粒度： (item_id, warehouse_id, batch_code)）

    本版本核心增强：
    ------------------------------------------
    1) 正式接入 expiry_resolver（生产日期 + 保质期 → 到期日期）
    2) 所有入库/盘盈自动推算 expiry_date
    3) 批次主档（batches）保证日期属性不被覆盖，但缺失时补齐
    4) 落账前做统一日期校验（exp >= prod）
    5) ledger + stocks 始终得到合法、单一来源的日期
    ------------------------------------------

    ✅ 第一阶段：scope（PROD/DRILL）账本隔离
    - 写入与读取都必须带 scope，否则 DRILL 会污染 PROD 的默认口径。
    """

    async def _ensure_batch_dict(
        self,
        *,
        session: AsyncSession,
        warehouse_id: int,
        item_id: int,
        batch_code: str,
        production_date: Optional[date],
        expiry_date: Optional[date],
        created_at: datetime,
    ) -> None:
        await ensure_batch_dict(
            session=session,
            warehouse_id=warehouse_id,
            item_id=item_id,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
            created_at=created_at,
        )

    async def _load_on_hand_qty(
        self,
        session: AsyncSession,
        *,
        scope: str,
        warehouse_id: int,
        item_id: int,
        batch_code: Optional[str],
    ) -> int:
        """
        读取当前库存槽位 qty（支持 NULL batch_code）。
        槽位不存在时视为 0。
        """
        sc = (scope or "").strip().upper()
        if sc not in {"PROD", "DRILL"}:
            raise ValueError("scope must be PROD|DRILL")

        row = (
            await session.execute(
                SA(
                    """
                    SELECT qty
                      FROM stocks
                     WHERE scope       = :sc
                       AND warehouse_id = :w
                       AND item_id      = :i
                       AND batch_code IS NOT DISTINCT FROM :c
                     LIMIT 1
                    """
                ),
                {"sc": sc, "w": int(warehouse_id), "i": int(item_id), "c": batch_code},
            )
        ).first()
        if not row:
            return 0
        try:
            return int(row[0] or 0)
        except Exception:
            return 0

    def _classify_adjust_value_error(self, msg: str) -> str:
        """
        把底层 ValueError（历史包袱）分类为：
        - insufficient_stock
        - batch_required
        - stock_adjust_reject（其它输入/约束）
        """
        m = (msg or "").strip()

        # 1) 明确的库存不足（底层使用英文固定短语）
        if "insufficient stock" in m.lower():
            return "insufficient_stock"

        # 2) 批次必填/批次不合法（中英文都兜）
        if ("batch_code" in m.lower()) or ("批次" in m):
            # 常见： "批次受控商品必须指定 batch_code。"
            if ("必须" in m) or ("required" in m.lower()):
                return "batch_required"
            return "stock_adjust_reject"

        # 3) 其它参数/约束类
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
        scope: str,
        warehouse_id: int,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        ✅ 第一阶段：scope 强制传递
        - 上层必须显式传 scope（PROD/DRILL）
        - 这样 DRILL 写入不会污染 PROD 的 stocks/ledger/snapshot

        统一异常语言收口（关键增强）：
        - 底层实现（adjust_impl）可能会在扣减失败/参数不合法时抛 ValueError（历史包袱/兼容）。
        - 在这里将其统一抬升为 Problem（HTTPException.detail=Problem），让上层不再依赖字符串判断。
        - HTTPException(detail=Problem) 必须原样透传（避免丢失 details/next_actions）。
        """
        sc = (scope or "").strip().upper()
        if sc not in {"PROD", "DRILL"}:
            raise ValueError("scope must be PROD|DRILL")

        try:
            return await adjust_impl(
                session=session,
                scope=sc,
                item_id=item_id,
                delta=delta,
                reason=reason,
                ref=ref,
                ref_line=ref_line,
                occurred_at=occurred_at,
                meta=meta,
                batch_code=batch_code,
                production_date=production_date,
                expiry_date=expiry_date,
                warehouse_id=warehouse_id,
                trace_id=trace_id,
                utc_now=lambda: datetime.now(UTC),
                ensure_batch_dict_fn=lambda s, w, i, c, p, e, t: self._ensure_batch_dict(
                    session=s,
                    warehouse_id=w,
                    item_id=i,
                    batch_code=c,
                    production_date=p,
                    expiry_date=e,
                    created_at=t,
                ),
            )
        except HTTPException:
            # ✅ Problem 化异常必须原样透传
            raise
        except ValueError as e:
            msg = str(e)
            kind = self._classify_adjust_value_error(msg)

            bc_norm = (str(batch_code).strip() if batch_code is not None else None) or None
            ctx = {
                "scope": sc,
                "ref": str(ref),
                "ref_line": (str(ref_line) if ref_line is not None else None),
                "warehouse_id": int(warehouse_id),
                "item_id": int(item_id),
                "batch_code": bc_norm,
                "delta": int(delta),
                "trace_id": trace_id,
                "raw_error": msg,
            }

            # ✅ 库存不足：409 shortage
            if kind == "insufficient_stock":
                if int(delta) < 0:
                    on_hand = await self._load_on_hand_qty(
                        session,
                        scope=sc,
                        warehouse_id=int(warehouse_id),
                        item_id=int(item_id),
                        batch_code=bc_norm,
                    )
                    required_qty = int(-int(delta))
                    short_qty = max(0, int(required_qty) - int(on_hand))
                else:
                    # 理论上 delta>=0 不应触发 insufficient，但做防御
                    on_hand = await self._load_on_hand_qty(
                        session,
                        scope=sc,
                        warehouse_id=int(warehouse_id),
                        item_id=int(item_id),
                        batch_code=bc_norm,
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
                            "batch_code": bc_norm,
                            "required_qty": int(required_qty),
                            "available_qty": int(on_hand),
                            "short_qty": int(short_qty),
                            "reason": "insufficient_stock",
                        }
                    ],
                    next_actions=[
                        {"action": "rescan_stock", "label": "刷新库存"},
                        {"action": "adjust_to_available", "label": "按可用库存调整数量"},
                    ],
                )

            # ✅ 批次类错误：422 batch_required（不应被误判为库存不足）
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
                            "batch_code": bc_norm,
                            "reason": msg,
                        }
                    ],
                )

            # ✅ 其它输入/约束：422 reject
            raise_problem(
                status_code=422,
                error_code="stock_adjust_reject",
                message="库存调整请求不合法。",
                context=ctx,
                details=[{"type": "validation", "path": "stock_adjust", "reason": msg}],
            )

    async def ship_commit_direct(
        self,
        session: AsyncSession,
        *,
        scope: str,
        warehouse_id: int,
        platform: str,
        shop_id: str,
        ref: str,
        lines: list[dict[str, int]],
        occurred_at: Optional[datetime] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        sc = (scope or "").strip().upper()
        if sc not in {"PROD", "DRILL"}:
            raise ValueError("scope must be PROD|DRILL")

        # ship_commit_direct_impl 内部会调用 adjust_fn，因此我们用闭包把 scope 固定进去
        async def _adjust_with_scope(*args: Any, **kwargs: Any) -> Dict[str, Any]:
            kwargs["scope"] = sc
            return await self.adjust(*args, **kwargs)

        return await ship_commit_direct_impl(
            session=session,
            warehouse_id=warehouse_id,
            platform=platform,
            shop_id=shop_id,
            ref=ref,
            lines=lines,
            occurred_at=occurred_at,
            trace_id=trace_id,
            utc_now=lambda: datetime.now(UTC),
            adjust_fn=_adjust_with_scope,
        )
