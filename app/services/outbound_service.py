# app/services/outbound_service.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock_service import StockService


class OutboundService:
    """
    v1.0 一步法出库（单仓，接口预留多仓）：

        commit(session, *, platform, shop_id, ref, lines, warehouse_id?)

    要点：
    - 扣减统一走 StockService.adjust(delta=-qty, reason="OUTBOUND", ref=ref)；
    - 幂等用 outbound_ship_ops 唯一键，冲突时做“台账判定+恢复”；
    - shop_id 为空时自动创建/复用占位门店满足外键；
    - 不使用外层事务，避免与 adjust 的事务管理冲突。
    """

    @staticmethod
    async def commit(
        session: AsyncSession,
        *,
        platform: str = "pdd",
        shop_id: str,
        ref: str,
        lines: List[Dict[str, Any]],
        refresh_visible: bool = False,
        warehouse_id: int | None = None,  # 预留，不参与单仓过滤
    ) -> Dict[str, Any]:
        store_id = await _resolve_store_id(session, platform=platform, shop_id=shop_id)
        if store_id is None:
            store_id = await _ensure_internal_store(session)
            await session.commit()

        results: List[Dict[str, Any]] = []
        svc = StockService()

        # 逐行处理（无外层事务）
        for line in lines:
            item_id = int(line["item_id"])
            loc_id = int(line["location_id"])
            need = int(line["qty"])

            # 1) 可用量检查
            avail_row = await session.execute(
                text("SELECT qty FROM stocks WHERE item_id=:iid AND location_id=:loc LIMIT 1"),
                {"iid": item_id, "loc": loc_id},
            )
            avail = avail_row.scalar_one_or_none()
            if avail is None:
                results.append({"item_id": item_id, "location_id": loc_id, "qty": 0, "status": "NO_STOCK"})
                continue
            if int(avail) < need:
                results.append({"item_id": item_id, "location_id": loc_id, "qty": 0, "status": "INSUFFICIENT_STOCK"})
                continue

            # 2) 幂等登记（硬幂等，冲突则尝试“台账判定+恢复”）
            inserted = await _insert_idempotency_row(
                session, store_id=store_id, ref=ref, item_id=item_id, location_id=loc_id, qty=need
            )
            await session.commit()  # 固化幂等登记
            if not inserted:
                # 已存在同键记录：判断是否已经扣减（依据台账 ref，如无 ref 列则按“未扣减”处理以恢复）
                if await _ledger_has_ref_column(session) and await _ledger_exists_with_ref(
                    session, ref=ref, item_id=item_id, location_id=loc_id
                ):
                    results.append({"item_id": item_id, "location_id": loc_id, "qty": 0, "status": "IDEMPOTENT"})
                    continue
                # 否则进行“恢复扣减”
                await svc.adjust(
                    session=session,
                    item_id=item_id,
                    location_id=loc_id,
                    delta=-need,
                    reason="OUTBOUND",
                    ref=ref,
                )
                results.append({"item_id": item_id, "location_id": loc_id, "qty": need, "status": "OK"})
                continue

            # 3) 正式扣减（首次路径）
            await svc.adjust(
                session=session,
                item_id=item_id,
                location_id=loc_id,
                delta=-need,
                reason="OUTBOUND",
                ref=ref,
            )
            results.append({"item_id": item_id, "location_id": loc_id, "qty": need, "status": "OK"})

        return {"store_id": store_id, "ref": ref, "results": results}


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
    """
    确保存在一个“内部占位门店”，返回其 id。
    """
    p = "__internal__"
    n = "__NO_STORE__"
    await session.execute(
        text("INSERT INTO stores(platform, name) VALUES (:p, :n) ON CONFLICT DO NOTHING"),
        {"p": p, "n": n},
    )
    row = await session.execute(
        text("SELECT id FROM stores WHERE platform=:p2 AND name=:n2 LIMIT 1"),
        {"p2": p, "n2": n},
    )
    sid = row.scalar_one()
    return int(sid)


async def _insert_idempotency_row(
    session: AsyncSession, *, store_id: int, ref: str, item_id: int, location_id: int, qty: int
) -> bool:
    """
    将 (store_id, ref, item_id, location_id) 写入幂等表；命中唯一键 → 返回 False。
    需要 outbound_ship_ops 上存在唯一约束 uq_ship_idem_key(store_id, ref, item_id, location_id)。
    """
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


async def _ledger_exists_with_ref(session: AsyncSession, *, ref: str, item_id: int, location_id: int) -> bool:
    # 台账中存在：reason='OUTBOUND' 且 ref=... 且 item、location 匹配
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
