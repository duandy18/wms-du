# app/services/outbound_service.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inventory_adjust import InventoryAdjust
from app.services.stock_service import StockService


class OutboundService:
    """
    v1.0 一步法出库（单仓，接口预留多仓）：
      commit(session, *, platform, shop_id, ref, warehouse_id, lines)

    要点：
    - FEFO 扣减：InventoryAdjust.fefo_outbound(delta 为负)
    - 幂等：outbound_ship_ops 上 (store_id, ref, item_id, location_id) 唯一
    - 可见性：末尾统一 flush + commit（适配外部可能已有事务上下文）
    - 可用量：读取 v_available（= on_hand - reservations.ACTIVE），避免多批次误判
    """

    @staticmethod
    async def commit(
        session: AsyncSession,
        platform: str,
        shop_id: str,
        *,
        ref: str,
        warehouse_id: int,
        lines: List[Dict[str, Any]],
        allow_expired: bool = False,
    ) -> Dict[str, Any]:
        if not lines:
            return {"ok": True, "total_lines": 0, "total_qty": 0}

        store_id = await _resolve_store_id(session, platform=platform, shop_id=shop_id)
        if store_id is None:
            store_id = await _ensure_internal_store(session)

        results: List[Dict[str, Any]] = []
        total_qty = 0
        svc = StockService()

        for ln in lines:
            item_id = int(ln["item_id"])
            location_id = int(ln["location_id"])
            qty = int(ln["qty"])

            if qty <= 0:
                results.append(
                    {"item_id": item_id, "location_id": location_id, "qty": 0, "status": "IGNORED"}
                )
                continue

            # 可用量检查：统一从 v_available 读取（现存-预留 的聚合口径）
            avail_row = await session.execute(
                text(
                    """
                    SELECT COALESCE(available, 0)
                    FROM v_available
                    WHERE item_id=:iid AND location_id=:loc
                    """
                ),
                {"iid": item_id, "loc": location_id},
            )
            avail = int(avail_row.scalar() or 0)
            if avail < qty:
                results.append(
                    {
                        "item_id": item_id,
                        "location_id": location_id,
                        "qty": 0,
                        "status": "INSUFFICIENT_STOCK",
                    }
                )
                continue

            # 幂等登记（命中唯一键→不再二次扣减）
            inserted = await _insert_idempotency_row(
                session,
                store_id=store_id,
                ref=ref,
                item_id=item_id,
                location_id=location_id,
                qty=qty,
            )
            if not inserted:
                if await _ledger_has_ref_column(session) and await _ledger_exists_with_ref(
                    session, ref=ref, item_id=item_id, location_id=location_id
                ):
                    results.append(
                        {
                            "item_id": item_id,
                            "location_id": location_id,
                            "qty": 0,
                            "status": "IDEMPOTENT",
                        }
                    )
                    continue
                # 未找到台账则补做一次扣减（仍在本次提交范畴内）
                await svc.adjust(
                    session=session,
                    item_id=item_id,
                    location_id=location_id,
                    delta=-qty,
                    reason="OUTBOUND",
                    ref=ref,
                )
                results.append(
                    {"item_id": item_id, "location_id": location_id, "qty": qty, "status": "OK"}
                )
                total_qty += qty
                continue

            # 正常路径：FEFO 扣减
            await InventoryAdjust.fefo_outbound(
                session=session,
                item_id=item_id,
                location_id=location_id,
                delta=-qty,
                reason="OUTBOUND",
                ref=ref,
                allow_expired=allow_expired,
            )
            results.append(
                {"item_id": item_id, "location_id": location_id, "qty": qty, "status": "OK"}
            )
            total_qty += qty

        await session.flush()
        await session.commit()

        return {
            "ok": True,
            "total_lines": len([r for r in results if r.get("status") == "OK"]),
            "total_qty": total_qty,
            "store_id": store_id,
            "ref": ref,
            "results": results,
        }


# ===================== 内部辅助 =====================


async def _resolve_store_id(session: AsyncSession, *, platform: str, shop_id: str) -> Optional[int]:
    if not shop_id:
        return None
    row = await session.execute(
        text("SELECT id FROM stores WHERE platform=:p AND name=:n LIMIT 1"),
        {"p": platform, "n": shop_id},
    )
    got = row.scalar_one_or_none()
    return int(got) if got is not None else None


async def _ensure_internal_store(session: AsyncSession) -> int:
    p, n = "__internal__", "__NO_STORE__"
    await session.execute(
        text("INSERT INTO stores(platform, name) VALUES (:p, :n) ON CONFLICT DO NOTHING"),
        {"p": p, "n": n},
    )
    row = await session.execute(
        text("SELECT id FROM stores WHERE platform=:p2 AND name=:n2 LIMIT 1"), {"p2": p, "n2": n}
    )
    return int(row.scalar_one())


async def _insert_idempotency_row(
    session: AsyncSession, *, store_id: int, ref: str, item_id: int, location_id: int, qty: int
) -> bool:
    rec = await session.execute(
        text(
            """
            INSERT INTO outbound_ship_ops (store_id, ref, item_id, location_id, qty)
            VALUES (:sid, :ref, :iid, :loc, :qty)
            ON CONFLICT ON CONSTRAINT uq_ship_idem_key DO NOTHING
            RETURNING id
            """
        ),
        {"sid": store_id, "ref": ref, "iid": item_id, "loc": location_id, "qty": qty},
    )
    return rec.scalar_one_or_none() is not None


async def _ledger_has_ref_column(session: AsyncSession) -> bool:
    row = await session.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='stock_ledger' AND column_name='ref'
            LIMIT 1
            """
        )
    )
    return row.first() is not None


async def _ledger_exists_with_ref(
    session: AsyncSession, *, ref: str, item_id: int, location_id: int
) -> bool:
    row = await session.execute(
        text(
            """
            SELECT 1
              FROM stock_ledger sl
              JOIN stocks s ON s.id = sl.stock_id
             WHERE sl.reason = 'OUTBOUND'
               AND sl.ref    = :ref
               AND sl.item_id = :iid
               AND s.location_id = :loc
             LIMIT 1
            """
        ),
        {"ref": ref, "iid": item_id, "loc": location_id},
    )
    return row.first() is not None


__all__ = ["OutboundService"]
