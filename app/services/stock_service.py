# app/services/stock_service.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Union

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.ledger_writer import write_ledger
from app.services.utils.expiry_resolver import resolve_batch_dates_for_item

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
    """

    # ------------------------------------------------------------------ #
    # 工具：确保 batch 主档存在                                           #
    # ------------------------------------------------------------------ #
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
        """
        若不存在批次主档则创建；若已存在，则不更新日期（避免覆盖历史业务档案）。

        注意：保持批次码为主键，不做基于日期的区分。
        """
        await session.execute(
            text(
                """
                INSERT INTO batches (
                    item_id,
                    warehouse_id,
                    batch_code,
                    production_date,
                    expiry_date,
                    created_at
                )
                VALUES (
                    :i, :w, :code, :prod, :exp, :created_at
                )
                ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
                """
            ),
            {
                "i": item_id,
                "w": int(warehouse_id),
                "code": batch_code,
                "prod": production_date,
                "exp": expiry_date,
                "created_at": created_at,
            },
        )

    # ------------------------------------------------------------------ #
    # 核心：带批次的增减（入库 / 出库 / 盘点）                            #
    # ------------------------------------------------------------------ #
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
    ) -> Dict[str, Any]:
        """
        批次增减（单一真实来源 stocks）；全量支持日期推导：

        - 入库(delta>0)：
              必须提供 batch_code；
              必须有日期（prod 或 exp），否则自动兜底 + 推导；
              若批次主档缺失，自动创建；
              批次主档日期缺失时可由本次补齐（但我们当前策略是不覆盖已有日期）。

        - 出库(delta<0)：
              只需要 batch_code；
              日期无需提供（不会改变批次元数据）。

        - 幂等：
              按 (wh, item, batch_code, reason, ref, ref_line) 判断。
        """
        reason_val = reason.value if isinstance(reason, MovementType) else str(reason)
        rl = int(ref_line) if ref_line is not None else 1
        ts = occurred_at or datetime.now(UTC)

        # ---------- 基础校验 ----------
        if delta == 0:
            return {"idempotent": True, "applied": False}

        if not batch_code or not str(batch_code).strip():
            raise ValueError("批次操作必须指定 batch_code。")
        batch_code = str(batch_code).strip()

        # 入库 & 盘盈：必须有日期（prod 或 exp），并做统一推算
        if delta > 0:
            if production_date is None and expiry_date is None:
                # 入库场景必须要有一个日期，这里交由解析器统一兜底
                production_date = production_date or date.today()

            # 统一解析：生产日期 + 保质期 → 到期日期
            production_date, expiry_date = await resolve_batch_dates_for_item(
                session=session,
                item_id=item_id,
                production_date=production_date,
                expiry_date=expiry_date,
            )

            # 日期合法性：exp >= prod
            if expiry_date is not None and production_date is not None:
                if expiry_date < production_date:
                    raise ValueError(
                        f"expiry_date({expiry_date}) < production_date({production_date})"
                    )

        # ---------- 幂等 ----------
        idem = await session.execute(
            text(
                """
                SELECT 1
                  FROM stock_ledger
                 WHERE warehouse_id = :w
                   AND item_id      = :i
                   AND batch_code   = :c
                   AND reason       = :r
                   AND ref          = :ref
                   AND ref_line     = :rl
                 LIMIT 1
                """
            ),
            {
                "w": int(warehouse_id),
                "i": item_id,
                "c": batch_code,
                "r": reason_val,
                "ref": ref,
                "rl": rl,
            },
        )
        if idem.scalar_one_or_none() is not None:
            return {"idempotent": True, "applied": False}

        # ---------- 入库：确保批次主档存在 ----------
        if delta > 0:
            await self._ensure_batch_dict(
                session=session,
                warehouse_id=warehouse_id,
                item_id=item_id,
                batch_code=batch_code,
                production_date=production_date,
                expiry_date=expiry_date,
                created_at=ts,
            )

        # ---------- 确保 stocks 槽位存在 ----------
        await session.execute(
            text(
                """
                INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
                VALUES (:i, :w, :c, 0)
                ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
                """
            ),
            {
                "i": item_id,
                "w": int(warehouse_id),
                "c": batch_code,
            },
        )

        # ---------- 加锁读取当前库存 ----------
        row = (
            (
                await session.execute(
                    text(
                        """
                        SELECT id AS sid, qty AS q
                          FROM stocks
                         WHERE item_id=:i AND warehouse_id=:w AND batch_code=:c
                         FOR UPDATE
                        """
                    ),
                    {"i": item_id, "w": int(warehouse_id), "c": batch_code},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise ValueError(
                f"stock slot missing for item={item_id}, wh={warehouse_id}, code={batch_code}"
            )

        stock_id, before_qty = int(row["sid"]), int(row["q"])
        new_qty = before_qty + int(delta)
        if new_qty < 0:
            raise ValueError(f"insufficient stock: before={before_qty}, delta={delta}")

        # ---------- 写台账（带上 trace_id + 日期） ----------
        await write_ledger(
            session=session,
            warehouse_id=int(warehouse_id),
            item_id=item_id,
            batch_code=batch_code,
            reason=reason_val,
            delta=int(delta),
            after_qty=new_qty,
            ref=ref,
            ref_line=rl,
            occurred_at=ts,
            trace_id=trace_id,
            production_date=production_date,
            expiry_date=expiry_date,
        )

        # ---------- 更新余额 ----------
        await session.execute(
            text("UPDATE stocks SET qty = qty + :d WHERE id = :sid"),
            {"d": int(delta), "sid": stock_id},
        )

        meta_out: Dict[str, Any] = dict(meta or {})
        if trace_id:
            meta_out.setdefault("trace_id", trace_id)

        return {
            "stock_id": stock_id,
            "before": before_qty,
            "delta": int(delta),
            "after": new_qty,
            "reason": reason_val,
            "ref": ref,
            "ref_line": rl,
            "meta": meta_out,
            "occurred_at": ts.isoformat(),
            "production_date": production_date,
            "expiry_date": expiry_date,
        }

    # ------------------------------------------------------------------ #
    # ship_commit_direct：按 FEFO 出库                                     #
    # ------------------------------------------------------------------ #
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
        """
        本方法保持原有行为，但 FEFO 选择更稳定（优先 expiry_date，再按 stock_id 排序）。
        """
        ts = occurred_at or datetime.now(UTC)

        # 聚合每个 item 的总需求
        need_by_item: Dict[int, int] = {}
        for line in lines or []:
            item = int(line["item_id"])
            qty = int(line["qty"])
            need_by_item[item] = need_by_item.get(item, 0) + qty

        if not need_by_item:
            return {"idempotent": True, "applied": False, "ref": ref, "total_qty": 0}

        idempotent = True
        total = 0

        for item_id, want in need_by_item.items():
            # 查已扣数量
            existing = await session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(delta), 0)
                      FROM stock_ledger
                     WHERE warehouse_id=:w AND item_id=:i
                       AND ref=:ref AND delta < 0
                    """
                ),
                {"w": int(warehouse_id), "i": item_id, "ref": ref},
            )
            already = int(existing.scalar() or 0)
            need = want + already
            if need <= 0:
                continue  # 已扣足

            idempotent = False
            remain = need

            # FEFO：按 expiry_date ASC + stock_id ASC
            while remain > 0:
                row = (
                    await session.execute(
                        text(
                            """
                            SELECT s.batch_code, s.qty
                              FROM stocks s
                              LEFT JOIN batches b
                                ON b.item_id = s.item_id
                               AND b.warehouse_id = s.warehouse_id
                               AND b.batch_code = s.batch_code
                             WHERE s.item_id=:i AND s.warehouse_id=:w AND s.qty>0
                             ORDER BY b.expiry_date ASC NULLS LAST, s.id ASC
                             LIMIT 1
                            """
                        ),
                        {"i": item_id, "w": int(warehouse_id)},
                    )
                ).first()

                if not row:
                    raise ValueError(f"insufficient stock for item={item_id}")

                batch_code, on_hand = str(row[0]), int(row[1])
                take = min(remain, on_hand)

                await self.adjust(
                    session=session,
                    item_id=item_id,
                    warehouse_id=warehouse_id,
                    delta=-take,
                    reason=MovementType.SHIP,
                    ref=ref,
                    ref_line=1,
                    occurred_at=ts,
                    batch_code=batch_code,
                    trace_id=trace_id,
                )

                remain -= take
                total += take

        return {
            "idempotent": idempotent,
            "applied": not idempotent,
            "ref": ref,
            "total_qty": total,
        }
