from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.reservation_service import ReservationError, ReservationService


# —— 默认批次：将无批次来源统一映射到 AUTO-{item}-{loc} —— #
async def _ensure_default_batch_id(
    session: AsyncSession, *, item_id: int, warehouse_id: int, location_id: int
) -> int:
    """
    返回稳定的“默认批次” id（已适配无 location_id 的 batches 结构）：

      - batch_code = f"AUTO-{item_id}-{location_id}"
      - 唯一口径： (item_id, warehouse_id, batch_code)
      - 不再依赖 batches.location_id 或任何带 loc 的唯一约束名
    """
    code = f"AUTO-{item_id}-{location_id}"

    # 1) 先按新口径查一次
    row = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM batches
                 WHERE item_id     = :item
                   AND warehouse_id = :wh
                   AND batch_code   = :code
                """
            ),
            {"item": item_id, "wh": warehouse_id, "code": code},
        )
    ).first()
    if row:
        return int(row[0])

    # 2) 插入（幂等），仅使用 (item_id, warehouse_id, batch_code)
    await session.execute(
        text(
            """
            INSERT INTO batches (item_id, warehouse_id, batch_code, expire_at)
            VALUES (:item, :wh, :code, NULL)
            ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
            """
        ),
        {"item": item_id, "wh": warehouse_id, "code": code},
    )

    # 3) 再查一次确认 id
    row = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM batches
                 WHERE item_id     = :item
                   AND warehouse_id = :wh
                   AND batch_code   = :code
                """
            ),
            {"item": item_id, "wh": warehouse_id, "code": code},
        )
    ).first()
    if not row:
        raise ReservationError("DATABASE_CONSISTENCY_ERROR")
    return int(row[0])


async def _allocate_locked_rows_default(
    session: AsyncSession, *, warehouse_id: int, item_id: int, need_qty: int
) -> List[Tuple[int, int, int]]:
    if need_qty <= 0:
        return []
    rows = (
        (
            await session.execute(
                text(
                    """
            SELECT s.id AS stock_id, s.location_id, s.qty AS on_hand
              FROM stocks s
              JOIN locations l ON l.id = s.location_id
             WHERE l.warehouse_id = :wh
               AND s.item_id = :item
               AND s.qty > 0
          ORDER BY s.qty DESC, s.location_id ASC
            FOR UPDATE OF s
        """
                ),
                {"wh": warehouse_id, "item": item_id},
            )
        )
        .mappings()
        .all()
    )
    plan: List[Tuple[int, int, int]] = []
    remain = int(need_qty)
    for r in rows:
        take = min(int(r["on_hand"]), remain)
        if take > 0:
            plan.append((int(r["stock_id"]), int(r["location_id"]), take))
            remain -= take
            if remain == 0:
                break
    if remain > 0:
        raise ReservationError("INSUFFICIENT_STOCK")
    return plan


async def _allocate_locked_rows_fefo(
    session: AsyncSession, *, warehouse_id: int, item_id: int, need_qty: int
) -> List[Tuple[int, int, int, Optional[int]]]:
    if need_qty <= 0:
        return []
    rows = (
        (
            await session.execute(
                text(
                    """
            SELECT s.id AS stock_id, s.location_id, s.qty AS on_hand, s.batch_id, b.expire_at
              FROM stocks s
              JOIN locations l ON l.id = s.location_id
              LEFT JOIN batches b ON b.id = s.batch_id
             WHERE l.warehouse_id = :wh
               AND s.item_id = :item
               AND s.qty > 0
          ORDER BY b.expire_at ASC NULLS LAST, s.location_id ASC
            FOR UPDATE OF s
        """
                ),
                {"wh": warehouse_id, "item": item_id},
            )
        )
        .mappings()
        .all()
    )
    plan: List[Tuple[int, int, int, Optional[int]]] = []
    remain = int(need_qty)
    for r in rows:
        take = min(int(r["on_hand"]), remain)
        if take > 0:
            plan.append((int(r["stock_id"]), int(r["location_id"]), take, r["batch_id"]))
            remain -= take
            if remain == 0:
                break
    if remain > 0:
        raise ReservationError("INSUFFICIENT_STOCK")
    return plan


async def lock(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
    occurred_at: Optional[datetime] = None,
    mode: str = "DEFAULT",  # "DEFAULT" | "FEFO"
) -> Dict[str, Any]:
    plat = platform.upper()
    rid, status, wh = await ReservationService.get_reservation_head(
        session, platform=plat, shop_id=shop_id, ref=ref
    )
    if status != "PLANNED":
        return {"status": "IDEMPOTENT", "reservation_id": rid}

    lines: List[Tuple[int, int]] = await ReservationService.fetch_reservation_lines(
        session, reservation_id=rid
    )

    use_fefo = (mode or "DEFAULT").upper() == "FEFO"
    total_need = 0
    allocations_fefo: List[Tuple[int, int, int, Optional[int], int]] = []
    allocations_def: List[Tuple[int, int, int, int]] = []

    for item_id, need in lines:
        need = int(need)
        total_need += need
        if use_fefo:
            rows = await _allocate_locked_rows_fefo(
                session, warehouse_id=wh, item_id=item_id, need_qty=need
            )
            allocations_fefo.extend((sid, loc, q, batch, item_id) for (sid, loc, q, batch) in rows)
        else:
            rows = await _allocate_locked_rows_default(
                session, warehouse_id=wh, item_id=item_id, need_qty=need
            )
            allocations_def.extend((sid, loc, q, item_id) for (sid, loc, q) in rows)

    now = occurred_at or datetime.now(timezone.utc)

    # 扣减 + 记账 + 写 allocations（统一写入非空 batch_id）
    if use_fefo:
        idx = 0
        for stock_id, location_id, take_qty, batch_id, item_id in allocations_fefo:
            idx += 1
            # 若分配到的行没有批次，先取默认批次（仓+批次；location 只用于编码）
            if batch_id is None:
                batch_id = await _ensure_default_batch_id(
                    session, item_id=item_id, warehouse_id=wh, location_id=location_id
                )

            after_qty = (
                await session.execute(
                    text("""UPDATE stocks SET qty = qty - :q WHERE id = :sid RETURNING qty"""),
                    {"sid": stock_id, "q": int(take_qty)},
                )
            ).scalar()
            if after_qty is None:
                raise ReservationError("DATABASE_CONSISTENCY_ERROR")

            await session.execute(
                text(
                    """
                    INSERT INTO stock_ledger
                        (reason, ref, ref_line, stock_id, item_id, location_id,
                         delta, after_qty, occurred_at, warehouse_id)
                    VALUES
                        ('RESERVE', :ref, :ln, :sid, :item, :loc,
                         :delta, :after, :at, :wh)
                """
                ),
                {
                    "ref": ref,
                    "ln": idx,
                    "sid": stock_id,
                    "item": item_id,
                    "loc": location_id,
                    "delta": -int(take_qty),
                    "after": after_qty,
                    "at": now,
                    "wh": wh,
                },
            )

            # allocations：统一用非空 batch_id，命中 NOT NULL partial unique
            await session.execute(
                text(
                    """
                    INSERT INTO reservation_allocations
                        (reservation_id, item_id, warehouse_id, location_id, batch_id, qty)
                    VALUES
                        (:rid, :item, :wh, :loc, :batch, :q)
                    ON CONFLICT (reservation_id, item_id, warehouse_id, batch_id)
                    WHERE batch_id IS NOT NULL
                    DO UPDATE SET qty = reservation_allocations.qty + EXCLUDED.qty
                """
                ),
                {
                    "rid": rid,
                    "item": item_id,
                    "wh": wh,
                    "loc": location_id,
                    "batch": batch_id,
                    "q": int(take_qty),
                },
            )
    else:
        idx = 0
        for stock_id, location_id, take_qty, item_id in allocations_def:
            idx += 1
            # DEFAULT 策略：没有 batch_id 时，为该 (item, loc) 取默认批次
            batch_id = await _ensure_default_batch_id(
                session, item_id=item_id, warehouse_id=wh, location_id=location_id
            )

            after_qty = (
                await session.execute(
                    text("""UPDATE stocks SET qty = qty - :q WHERE id = :sid RETURNING qty"""),
                    {"sid": stock_id, "q": int(take_qty)},
                )
            ).scalar()
            if after_qty is None:
                raise ReservationError("DATABASE_CONSISTENCY_ERROR")

            await session.execute(
                text(
                    """
                    INSERT INTO stock_ledger
                        (reason, ref, ref_line, stock_id, item_id, location_id,
                         delta, after_qty, occurred_at, warehouse_id)
                    VALUES
                        ('RESERVE', :ref, :ln, :sid, :item, :loc,
                         :delta, :after, :at, :wh)
                """
                ),
                {
                    "ref": ref,
                    "ln": idx,
                    "sid": stock_id,
                    "item": item_id,
                    "loc": location_id,
                    "delta": -int(take_qty),
                    "after": after_qty,
                    "at": now,
                    "wh": wh,
                },
            )

            await session.execute(
                text(
                    """
                    INSERT INTO reservation_allocations
                        (reservation_id, item_id, warehouse_id, location_id, batch_id, qty)
                    VALUES
                        (:rid, :item, :wh, :loc, :batch, :q)
                    ON CONFLICT (reservation_id, item_id, warehouse_id, batch_id)
                    WHERE batch_id IS NOT NULL
                    DO UPDATE SET qty = reservation_allocations.qty + EXCLUDED.qty
                """
                ),
                {
                    "rid": rid,
                    "item": item_id,
                    "wh": wh,
                    "loc": location_id,
                    "batch": batch_id,
                    "q": int(take_qty),
                },
            )

    await session.execute(
        text("""UPDATE reservations SET status='LOCKED', locked_qty=:q WHERE id=:rid"""),
        {"rid": rid, "q": int(total_need)},
    )
    await ReservationService.audit(session, ref=ref, event="LOCK", platform=plat, shop_id=shop_id)
    return {
        "status": "OK",
        "reservation_id": rid,
        "locked_qty": int(total_need),
        "mode": (mode or "DEFAULT").upper(),
    }
