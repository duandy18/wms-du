# tests/helpers/phase4_routing_helpers.py
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

UTC = timezone.utc


async def ensure_two_warehouses(session: AsyncSession) -> Tuple[int, int]:
    """
    获取两个 warehouse_id。若现有不足则动态插入测试仓。
    兼容 warehouses 表可能存在 NOT NULL 且无默认值的列。
    """
    rows = await session.execute(text("SELECT id FROM warehouses ORDER BY id"))
    ids = [int(r[0]) for r in rows.fetchall()]

    needed = 2 - len(ids)
    if needed <= 0:
        return ids[0], ids[1]

    cols_rows = await session.execute(
        text(
            """
            SELECT column_name, data_type
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name   = 'warehouses'
               AND is_nullable  = 'NO'
               AND column_default IS NULL
               AND column_name <> 'id'
            """
        )
    )
    col_info = [(str(r[0]), str(r[1])) for r in cols_rows.fetchall()]

    if not col_info:
        for _ in range(needed):
            row = await session.execute(text("INSERT INTO warehouses DEFAULT VALUES RETURNING id"))
            ids.append(int(row.scalar()))
        return ids[0], ids[1]

    columns = ", ".join(c for c, _ in col_info)
    placeholders = ", ".join(f":{c}" for c, _ in col_info)
    sql = f"INSERT INTO warehouses ({columns}) VALUES ({placeholders}) RETURNING id"

    for _ in range(needed):
        params = {}
        for col, dtype in col_info:
            dt = dtype.lower()
            if "char" in dt or "text" in dt:
                params[col] = f"WH-{col}-{uuid.uuid4().hex[:8]}"
            elif "int" in dt:
                params[col] = 0
            elif "bool" in dt:
                params[col] = False
            elif "timestamp" in dt or "time" in dt:
                params[col] = datetime.now(UTC)
            elif dt == "date":
                params[col] = datetime.now(UTC).date()
            else:
                params[col] = f"WH-{col}-{uuid.uuid4().hex[:4]}"
        row = await session.execute(text(sql), params)
        ids.append(int(row.scalar()))

    return ids[0], ids[1]


async def ensure_store(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    name: str,
    route_mode: Optional[str] = None,
) -> int:
    """
    确保 stores(platform, shop_id) 存在，并可选更新 route_mode。
    """
    plat = platform.upper()

    row = await session.execute(
        text("SELECT id FROM stores WHERE platform=:p AND shop_id=:s LIMIT 1"),
        {"p": plat, "s": shop_id},
    )
    sid = row.scalar()

    if sid is None:
        if route_mode is None:
            await session.execute(
                text(
                    """
                    INSERT INTO stores (platform, shop_id, name)
                    VALUES (:p, :s, :n)
                    ON CONFLICT (platform, shop_id) DO NOTHING
                    """
                ),
                {"p": plat, "s": shop_id, "n": name},
            )
        else:
            await session.execute(
                text(
                    """
                    INSERT INTO stores (platform, shop_id, name, route_mode)
                    VALUES (:p, :s, :n, :m)
                    ON CONFLICT (platform, shop_id) DO NOTHING
                    """
                ),
                {"p": plat, "s": shop_id, "n": name, "m": route_mode},
            )
        row2 = await session.execute(
            text("SELECT id FROM stores WHERE platform=:p AND shop_id=:s LIMIT 1"),
            {"p": plat, "s": shop_id},
        )
        sid = row2.scalar()
        if sid is None:
            raise RuntimeError(f"failed to ensure store: {plat}/{shop_id}")

    if route_mode is not None:
        await session.execute(
            text("UPDATE stores SET route_mode=:m WHERE id=:sid"),
            {"m": route_mode, "sid": int(sid)},
        )

    return int(sid)


async def bind_store_warehouses(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    top_warehouse_id: int,
    backup_warehouse_id: int,
    route_mode: Optional[str] = None,
) -> int:
    """
    ✅ 统一世界观：store_warehouse 是“候选能力声明 + 排序偏好”。

    返回 store_id。
    """
    store_id = await ensure_store(
        session,
        platform=platform,
        shop_id=shop_id,
        name=f"UT-{platform.upper()}-{shop_id}",
        route_mode=route_mode,
    )

    await session.execute(
        text("DELETE FROM store_warehouse WHERE store_id=:sid"),
        {"sid": store_id},
    )
    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, :wid, TRUE, 10)
            """
        ),
        {"sid": store_id, "wid": int(top_warehouse_id)},
    )
    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, :wid, FALSE, 20)
            """
        ),
        {"sid": store_id, "wid": int(backup_warehouse_id)},
    )
    return int(store_id)


async def ensure_store_province_route(
    session: AsyncSession,
    *,
    store_id: int,
    province: str,
    warehouse_id: int,
    priority: int = 10,
    active: bool = True,
) -> None:
    """
    ✅ 统一世界观：store_province_routes = 省 → 候选仓裁剪器。

    约束：
    - route 引用仓必须属于 store_warehouse（测试里通常已 bind_store_warehouses）
    """
    prov = str(province)

    await session.execute(
        text("DELETE FROM store_province_routes WHERE store_id=:sid AND province=:prov"),
        {"sid": int(store_id), "prov": prov},
    )
    await session.execute(
        text(
            """
            INSERT INTO store_province_routes (store_id, province, warehouse_id, priority, active)
            VALUES (:sid, :prov, :wid, :prio, :active)
            """
        ),
        {
            "sid": int(store_id),
            "prov": prov,
            "wid": int(warehouse_id),
            "prio": int(priority),
            "active": bool(active),
        },
    )

def make_address(province: str = "UT-PROV") -> dict:
    """Standard test address payload for Phase 4 routing worldview."""
    return {"province": province, "receiver_name": "X", "receiver_phone": "000"}
