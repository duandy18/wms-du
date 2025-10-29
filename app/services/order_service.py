# app/services/order_service.py
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store import Store, StoreItem
from app.services.channel_inventory_service import ChannelInventoryService
from app.services.outbound_service import OutboundService
from app.services.store_service import StoreService


_TWO = Decimal("0.01")


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


class OrderService:
    """
    v1.0 订单薄服务（异步 · 强契约）：

    - reserve():   下单占用（仅维护 ChannelInventory.reserved_qty，不动 stocks/ledger）
    - cancel():    取消占用（释放 reserved）
    - ship():      发货扣减（调用 OutboundService.commit：行锁扣减 + 写台账 + 释放 reserved + 刷新可见量）

    金额语义（新增）：
    - 行可包含 unit_price（非负，2dp），返回行的 line_amount = qty * unit_price 以及订单金额汇总 order_amount。
    - 仅参与返回值与上层业务展示，不直接写入 order_items（维持 v1.0 分层，避免越权修改）。
    """

    # ------------------------------------------------------------------
    # 下单占用：把各行的 reserved_qty 增加（不动 stocks / 不写 ledger）
    # ------------------------------------------------------------------
    @staticmethod
    async def reserve(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        ref: str,
        lines: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        下单占用：
        lines: [{item_id, qty, unit_price?}, ...]
        仅调整 ChannelInventory.reserved_qty（+qty），不写台账，不动 stocks。
        返回：附带 order_amount 与每行 line_amount。
        """
        store_id = await _resolve_store_id(session, platform=platform, shop_id=shop_id)
        norm_lines, order_amount = _normalize_lines_with_money(lines)
        results: List[Dict[str, Any]] = []

        tx_ctx = session.begin_nested() if session.in_transaction() else session.begin()
        async with tx_ctx:
            for line in norm_lines:
                item_id = int(line["item_id"])
                qty = int(line["qty"])

                await _ensure_store_item_mapping(session, store_id=store_id, item_id=item_id)

                new_reserved = await ChannelInventoryService.adjust_reserved(
                    session, store_id=store_id, item_id=item_id, delta=+qty
                )
                results.append({
                    "item_id": item_id,
                    "reserved": +qty,
                    "reserved_total": int(new_reserved),
                    "unit_price": line["unit_price"],
                    "line_amount": line["line_amount"],
                    "status": "OK",
                })

        # 可选刷新 visible
        try:
            ok_items = [r["item_id"] for r in results if r["status"] == "OK"]
            if ok_items:
                await StoreService.refresh_channel_inventory_for_store(
                    session, store_id=store_id, item_ids=ok_items, dry_run=False
                )
        except Exception:
            pass

        return {
            "store_id": store_id,
            "ref": ref,
            "order_amount": order_amount,
            "results": results,
            "occurred_at": datetime.now(UTC).isoformat(),
        }

    # ------------------------------------------------------------------
    # 取消占用：把 reserved_qty 回退（不动 stocks / 不写 ledger）
    # ------------------------------------------------------------------
    @staticmethod
    async def cancel(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        ref: str,
        lines: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        取消占用：
        lines: [{item_id, qty, unit_price?}, ...]
        仅调整 ChannelInventory.reserved_qty（-qty），不写台账，不动 stocks。
        返回：附带 order_amount 与每行 line_amount（便于前端回显/流水一致）。
        """
        store_id = await _resolve_store_id(session, platform=platform, shop_id=shop_id)
        norm_lines, order_amount = _normalize_lines_with_money(lines)
        results: List[Dict[str, Any]] = []

        tx_ctx = session.begin_nested() if session.in_transaction() else session.begin()
        async with tx_ctx:
            for line in norm_lines:
                item_id = int(line["item_id"])
                qty = int(line["qty"])

                await _ensure_store_item_mapping(session, store_id=store_id, item_id=item_id)

                new_reserved = await ChannelInventoryService.adjust_reserved(
                    session, store_id=store_id, item_id=item_id, delta=-qty
                )
                results.append({
                    "item_id": item_id,
                    "released": qty,
                    "reserved_total": int(new_reserved),
                    "unit_price": line["unit_price"],
                    "line_amount": line["line_amount"],
                    "status": "OK",
                })

        # 可选刷新 visible
        try:
            ok_items = [r["item_id"] for r in results if r["status"] == "OK"]
            if ok_items:
                await StoreService.refresh_channel_inventory_for_store(
                    session, store_id=store_id, item_ids=ok_items, dry_run=False
                )
        except Exception:
            pass

        return {
            "store_id": store_id,
            "ref": ref,
            "order_amount": order_amount,
            "results": results,
            "occurred_at": datetime.now(UTC).isoformat(),
        }

    # ------------------------------------------------------------------
    # 发货扣减：调用 OutboundService.commit 完成扣减 + 写台账 + 释放占用
    # ------------------------------------------------------------------
    @staticmethod
    async def ship(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        ref: str,
        lines: List[Dict[str, Any]],
        refresh_visible: bool = True,
        warehouse_id: int | None = None,
    ) -> Dict[str, Any]:
        """
        发货扣减（最终出库）：
        lines: [{item_id, location_id, qty, unit_price?}, ...]
        - 交给 OutboundService.commit()：行锁扣减 stocks，写 OUTBOUND 台账，并对该店 reserved 做 -qty
        - 我们只在返回值中附带金额（行的 line_amount 与订单总额），不改变出库与台账逻辑
        """
        # 先确保映射存在（避免在 commit 内因映射缺失无法刷新 visible）
        store_id = await _resolve_store_id(session, platform=platform, shop_id=shop_id)

        # 金额规范化（不影响出库路由）
        norm_lines, order_amount = _normalize_lines_with_money(lines)

        for line in norm_lines:
            await _ensure_store_item_mapping(session, store_id=store_id, item_id=int(line["item_id"]))

        # 出库：交给 OutboundService 完成扣减 + 台账 + reserved 释放 + 可选刷新 visible
        # 注意：不要把金额字段传入扣减层（保持 v1.0 职责分离）
        result = await OutboundService.commit(
            session,
            platform=platform,
            shop_id=shop_id,
            ref=ref,
            lines=[{"item_id": l["item_id"], "location_id": l.get("location_id"), "qty": l["qty"]} for l in norm_lines],
            refresh_visible=refresh_visible,
            warehouse_id=warehouse_id,
        )
        result["occurred_at"] = datetime.now(UTC).isoformat()
        result["order_amount"] = order_amount
        result["lines"] = norm_lines  # 回显金额与 qty 规范化结果
        return result


# ======================================================================
#                            内部帮助函数
# ======================================================================

async def _resolve_store_id(session: AsyncSession, *, platform: str, shop_id: str) -> int:
    """
    解析 store_id（按你当前模型：platform + name）。
    若不存在则抛出异常，保证调用方显式建店。
    """
    if not shop_id:
        raise ValueError("shop_id is required")
    sid = (
        await session.execute(
            select(Store.id).where(Store.platform == platform, Store.name == shop_id).limit(1)
        )
    ).scalar_one_or_none()
    if sid is None:
        # 显式失败，避免静默创建导致意外脏数据
        raise ValueError(f"store not found: platform={platform}, shop_id={shop_id}")
    return int(sid)


async def _ensure_store_item_mapping(session: AsyncSession, *, store_id: int, item_id: int) -> None:
    """
    确保 (store_id, item_id) 绑定存在；若不存在自动建立空映射，便于 reserved/visible 正常工作。
    """
    exists = (
        await session.execute(
            select(StoreItem.id).where(StoreItem.store_id == store_id, StoreItem.item_id == item_id)
        )
    ).scalar_one_or_none()
    if exists is not None:
        return
    # 只创建映射，不设置 cap/pdd_sku 等字段（按需后续补充）
    await StoreService.upsert_store_item(session, store_id=store_id, item_id=item_id)
