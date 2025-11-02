# app/services/order_service.py
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Dict, List, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.outbound_service import OutboundService


_TWO = Decimal("0.01")


# ================================ 金额与行规范化 ================================

def _to_decimal(val: Any, *, nonneg: bool = True) -> Decimal:
    """
    金额规范化：接受 str/int/float/Decimal，转为 Decimal(2dp, 四舍五入)。
    """
    if val is None:
        d = Decimal("0")
    elif isinstance(val, Decimal):
        d = val
    else:
        try:
            d = Decimal(str(val))
        except (InvalidOperation, ValueError):
            raise ValueError(f"invalid decimal: {val!r}")
    if nonneg and d < 0:
        raise ValueError(f"negative money not allowed: {d}")
    return d.quantize(_TWO, rounding=ROUND_HALF_UP)


def _normalize_lines_with_money(lines: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Decimal]:
    """
    规范化行：
      - qty: int > 0
      - unit_price: Decimal(>=0, 2dp)
      - line_amount = qty * unit_price（2dp）
    返回：(规范化后的行列表, 订单总金额)
    """
    norm: List[Dict[str, Any]] = []
    total = Decimal("0.00")
    for line in lines:
        item_id = int(line["item_id"])
        qty = int(line["qty"])
        if qty <= 0:
            raise ValueError(f"qty must be positive for item_id={item_id}")
        unit_price = _to_decimal(line.get("unit_price", 0))
        line_amount = (Decimal(qty) * unit_price).quantize(_TWO, rounding=ROUND_HALF_UP)
        total += line_amount
        n = dict(line)
        n["item_id"] = item_id
        n["qty"] = qty
        n["unit_price"] = unit_price
        n["line_amount"] = line_amount
        norm.append(n)
    total = total.quantize(_TWO, rounding=ROUND_HALF_UP)
    return norm, total


# ================================== 服务主体 ==================================

class OrderService:
    """
    订单服务 · 核心收口（无店铺可见量耦合）

    - create_order(): 生成最简订单头/行（行固定列名 req_qty）
    - reserve(order_id): 仅写批次级 reservations（FEFO 分摊），不扣库存/不写台账
    - cancel(order_id): 释放该订单的 reservations
    - ship(...): 调用 OutboundService.commit 真正扣减、写台账；强制 refresh_visible=False
    """

    # ------------------------------------------------------------------
    # 最简订单生成（供测试/流程驱动；不落仓库字段）
    # ------------------------------------------------------------------
    @staticmethod
    async def create_order(
        session: AsyncSession,
        *,
        item_id: int,
        warehouse_id: int,  # 为兼容测试入参保留，但不持久化（仓库选择属于履约阶段）
        qty: int,
        client_ref: str,
    ) -> int:
        """
        创建一个最简订单头+行，返回 order_id。
        订单头不写仓库；订单行固定写 req_qty。
        """
        tx_ctx = session.begin_nested() if session.in_transaction() else session.begin()
        async with tx_ctx:
            # 1) 订单头（不写仓库）
            res = await session.execute(
                text(
                    """
                    INSERT INTO orders (client_ref, status, created_at)
                    VALUES (:ref, 'CREATED', NOW())
                    RETURNING id
                    """
                ),
                {"ref": client_ref},
            )
            order_id = int(res.scalar_one())

            # 2) 单行（固定列名 req_qty）
            await session.execute(
                text(
                    """
                    INSERT INTO order_lines (order_id, item_id, req_qty)
                    VALUES (:oid, :item, :qty)
                    """
                ),
                {"oid": order_id, "item": int(item_id), "qty": int(qty)},
            )

        await session.commit()
        return order_id

    # ------------------------------------------------------------------
    # 按订单号预留：FEFO 分摊到 batches，仅写 reservations（不扣库存/不写台账）
    # ------------------------------------------------------------------
    @staticmethod
    async def reserve(
        session: AsyncSession,
        *,
        order_id: int,
    ) -> Dict[str, Any]:
        """
        按 order_id 执行 FEFO 预留：
        - 读取 order_lines(order_id, item_id, req_qty)
        - 按 FEFO（expire_at ASC, id ASC）在各批次以「可分配量 = stocks − reservations」为上限分摊
        - 写 reservations(order_id, item_id, batch_id, location_id, qty, status='ACTIVE', ref)
        """
        # 1) 读取订单行
        rows = (
            await session.execute(
                text("SELECT item_id, req_qty FROM order_lines WHERE order_id = :oid"),
                {"oid": int(order_id)},
            )
        ).all()
        if not rows:
            raise ValueError(f"no order_lines for order_id={order_id}")

        allocations: List[Dict[str, Any]] = []

        tx_ctx = session.begin_nested() if session.in_transaction() else session.begin()
        async with tx_ctx:
            for item_id, req_qty in rows:
                remaining = int(req_qty)

                # 2) FEFO 批次可分配量：available = onhand(stocks) - reserved(reservations)
                fefo_rs = await session.execute(
                    text(
                        """
                        WITH onhand AS (
                          SELECT s.batch_id, COALESCE(SUM(s.qty),0) AS qty
                          FROM stocks s
                          JOIN batches b ON b.id = s.batch_id
                          WHERE b.item_id = :item
                          GROUP BY s.batch_id
                        ),
                        reserved AS (
                          SELECT r.batch_id, COALESCE(SUM(r.qty),0) AS qty
                          FROM reservations r
                          JOIN batches b ON b.id = r.batch_id
                          WHERE b.item_id = :item
                          GROUP BY r.batch_id
                        )
                        SELECT
                          b.id          AS batch_id,
                          b.location_id AS loc,
                          COALESCE(o.qty,0) - COALESCE(r.qty,0) AS available,
                          b.expire_at
                        FROM batches b
                        LEFT JOIN onhand   o ON o.batch_id = b.id
                        LEFT JOIN reserved r ON r.batch_id = b.id
                        WHERE b.item_id = :item
                        ORDER BY b.expire_at NULLS LAST, b.id
                        """
                    ),
                    {"item": int(item_id)},
                )

                for row in fefo_rs:
                    bid = int(row.batch_id)
                    loc = int(row.loc)
                    avail = int(row.available or 0)
                    if remaining <= 0:
                        break
                    if avail <= 0:
                        continue

                    take = min(remaining, avail)

                    # 3) 写 reservations（批次级占位：含 location_id，显式 ACTIVE）
                    await session.execute(
                        text(
                            """
                            INSERT INTO reservations
                              (order_id, item_id, batch_id, location_id, qty, status, ref)
                            VALUES
                              (:oid, :item, :bid, :loc, :qty, 'ACTIVE', :ref)
                            """
                        ),
                        {
                            "oid": int(order_id),
                            "item": int(item_id),
                            "bid": bid,
                            "loc": loc,
                            "qty": int(take),
                            # 改为批次唯一的 ref，避免撞 UNIQUE(ref, item_id, location_id)
                            "ref": f"OID:{order_id}:{item_id}:{bid}",
                        },
                    )

                    allocations.append(
                        {"item_id": int(item_id), "batch_id": bid, "location_id": loc, "qty": int(take)}
                    )
                    remaining -= take

                if remaining > 0:
                    raise ValueError(
                        f"insufficient stock for item_id={item_id}, need={req_qty}"
                    )

        await session.commit()
        return {
            "order_id": int(order_id),
            "allocations": allocations,
            "occurred_at": datetime.now(UTC).isoformat(),
            "mode": "reserve_by_order",
        }

    # ------------------------------------------------------------------
    # 按订单号取消预留：删除 reservations 中该订单的记录
    # ------------------------------------------------------------------
    @staticmethod
    async def cancel(
        session: AsyncSession,
        *,
        order_id: int,
    ) -> Dict[str, Any]:
        """
        按 order_id 取消预留：删除该单在 reservations 的记录（全量释放占位）。
        """
        tx_ctx = session.begin_nested() if session.in_transaction() else session.begin()
        async with tx_ctx:
            await session.execute(
                text("DELETE FROM reservations WHERE order_id = :oid"),
                {"oid": int(order_id)},
            )
        await session.commit()
        return {
            "order_id": int(order_id),
            "released": True,
            "occurred_at": datetime.now(UTC).isoformat(),
            "mode": "cancel_by_order",
        }

    # ------------------------------------------------------------------
    # 发货扣减：调用 OutboundService.commit 完成扣减 + 写台账；与平台展示彻底解耦
    # ------------------------------------------------------------------
    @staticmethod
    async def ship(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        ref: str,
        lines: List[Dict[str, Any]],
        refresh_visible: bool = False,  # 缺省关闭，且下传时强制 False
        warehouse_id: int | None = None,
    ) -> Dict[str, Any]:
        """
        发货扣减（最终出库）：
        lines: [{item_id, location_id, qty, unit_price?}, ...]
        - 交给 OutboundService.commit()：行锁扣减 stocks，写 OUTBOUND 台账，并释放该单 reservations
        - 不做任何店铺可见量刷新（完全与平台展示解耦）
        """
        # 金额规范化（只在返回值中展示，不参与扣减层）
        norm_lines, order_amount = _normalize_lines_with_money(lines)

        # 出库：交给 OutboundService 完成扣减 + 台账 + reservations 释放
        result = await OutboundService.commit(
            session,
            platform=platform,
            shop_id=shop_id,
            ref=ref,
            lines=[
                {
                    "item_id": l["item_id"],
                    "location_id": l.get("location_id"),
                    "qty": l["qty"],
                }
                for l in norm_lines
            ],
            refresh_visible=False,  # 与平台展示彻底解耦
            warehouse_id=warehouse_id,
        )
        result["occurred_at"] = datetime.now(UTC).isoformat()
        result["order_amount"] = order_amount
        result["lines"] = norm_lines  # 回显金额与 qty 规范化结果
        return result
