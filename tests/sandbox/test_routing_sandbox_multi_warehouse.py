# tests/sandbox/test_routing_sandbox_multi_warehouse.py

import random
from dataclasses import dataclass
from typing import List, Tuple

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService


@dataclass
class SandboxOrderLine:
    item_id: int
    qty: int


@dataclass
class SandboxOrder:
    platform: str
    shop_id: str
    ext_order_id: str
    lines: List[SandboxOrderLine]


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------


async def _ensure_n_warehouses(session: AsyncSession, n: int) -> List[int]:
    """
    返回至少 n 个 warehouse_id。
    若现有不足则动态插入测试仓，兼容 warehouses 表可能存在 NOT NULL 且无默认值的列。
    """
    rows = await session.execute(sa.text("SELECT id FROM warehouses ORDER BY id"))
    ids = [int(r[0]) for r in rows.fetchall()]

    needed = int(n) - len(ids)
    if needed <= 0:
        return ids[:n]

    cols_rows = await session.execute(
        sa.text(
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
            row = await session.execute(sa.text("INSERT INTO warehouses DEFAULT VALUES RETURNING id"))
            ids.append(int(row.scalar()))
        return ids[:n]

    columns = ", ".join(c for c, _ in col_info)
    placeholders = ", ".join(f":{c}" for c, _ in col_info)
    sql = f"INSERT INTO warehouses ({columns}) VALUES ({placeholders}) RETURNING id"

    import uuid
    from datetime import datetime, timezone

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
                params[col] = datetime.now(timezone.utc)
            elif dt == "date":
                params[col] = datetime.now(timezone.utc).date()
            else:
                params[col] = f"WH-{col}-{uuid.uuid4().hex[:4]}"
        row = await session.execute(sa.text(sql), params)
        ids.append(int(row.scalar()))

    return ids[:n]


async def _pick_existing_item_ids(session: AsyncSession, n: int = 3) -> List[int]:
    """
    从测试基线（seed_test_baseline）已存在的 items 中挑选若干个 item_id，
    避免在沙盘测试里硬插 items 导致 NOT NULL/约束漂移。
    """
    rows = await session.execute(sa.text("SELECT id FROM items ORDER BY id ASC LIMIT :n"), {"n": int(n)})
    ids = [int(r[0]) for r in rows.fetchall()]
    if len(ids) < n:
        raise RuntimeError(f"sandbox requires at least {n} seeded items, got {ids}")
    return ids


async def seed_world_phase5(session: AsyncSession) -> Tuple[int, int, int]:
    """
    Phase 5 服务归属沙盘初始化：

    - 仓库：至少 3 个（返回 wh1/wh2/wh3）
    - 店铺：S1, S2, S3
    - 服务省份映射（warehouse_service_provinces）：
        P-S1 -> wh2
        P-S2 -> wh3
        P-S3 -> （故意不配置，制造 BLOCKED）
    """
    wh_ids = await _ensure_n_warehouses(session, 3)
    wh1, wh2, wh3 = int(wh_ids[0]), int(wh_ids[1]), int(wh_ids[2])

    # 确保 stores 存在（name NOT NULL）
    await session.execute(
        sa.text(
            """
            INSERT INTO stores (platform, shop_id, name, active)
            VALUES
              ('PDD','S1','S1',TRUE),
              ('PDD','S2','S2',TRUE),
              ('PDD','S3','S3',TRUE)
            ON CONFLICT (platform, shop_id) DO NOTHING;
            """
        )
    )

    # 服务省份：P-S1 -> wh2, P-S2 -> wh3
    await session.execute(
        sa.text(
            """
            INSERT INTO warehouse_service_provinces (warehouse_id, province_code)
            VALUES (:w2, 'P-S1')
            ON CONFLICT (province_code) DO UPDATE SET warehouse_id = EXCLUDED.warehouse_id;
            """
        ),
        {"w2": wh2},
    )
    await session.execute(
        sa.text(
            """
            INSERT INTO warehouse_service_provinces (warehouse_id, province_code)
            VALUES (:w3, 'P-S2')
            ON CONFLICT (province_code) DO UPDATE SET warehouse_id = EXCLUDED.warehouse_id;
            """
        ),
        {"w3": wh3},
    )

    await session.commit()
    return wh1, wh2, wh3


def generate_orders(n: int, *, item_ids: List[int]) -> List[SandboxOrder]:
    """
    随机生成订单（只跑 ingest）。
    为了可复现，外部调用前应设定 random.seed。
    """
    shops = ["S1", "S2", "S3"]
    if not item_ids:
        raise ValueError("item_ids must not be empty")

    orders: List[SandboxOrder] = []
    for i in range(n):
        shop = random.choice(shops)
        lines = [
            SandboxOrderLine(item_id=int(random.choice(item_ids)), qty=random.randint(1, 8))
            for _ in range(random.randint(1, 3))
        ]
        orders.append(
            SandboxOrder(
                platform="PDD",
                shop_id=shop,
                ext_order_id=f"SANDBOX-{i:04d}",
                lines=lines,
            )
        )
    return orders


async def collect_order_summary_phase5(session: AsyncSession):
    """
    Phase 5：从 orders + order_fulfillment 聚合“服务归属事实 / 阻断事实”。

    兼容口径：
      - service_warehouse_id := order_fulfillment.planned_warehouse_id
      - fulfillment_status  := order_fulfillment.fulfillment_status
    """
    res = await session.execute(
        sa.text(
            """
            SELECT
              o.platform,
              o.shop_id,
              f.fulfillment_status AS fulfillment_status,
              COALESCE(f.planned_warehouse_id, 0) AS service_warehouse_id,
              COUNT(*) AS n
            FROM orders o
            LEFT JOIN order_fulfillment f ON f.order_id = o.id
            GROUP BY o.platform, o.shop_id, f.fulfillment_status, COALESCE(f.planned_warehouse_id, 0)
            ORDER BY o.platform, o.shop_id, f.fulfillment_status, COALESCE(f.planned_warehouse_id, 0);
            """
        )
    )
    return res.fetchall()


# ---------------------------------------------------------
# Test
# ---------------------------------------------------------


@pytest.mark.asyncio
async def test_routing_sandbox_ingest_only(
    db_session_like_pg: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Phase 5 沙盘：只跑 ingest，不碰 reserve/ship。

    验证：
    - S1：province=P-S1 命中服务仓 wh2 => SERVICE_ASSIGNED（service_warehouse_id=wh2）
    - S2：province=P-S2 命中服务仓 wh3 => SERVICE_ASSIGNED（service_warehouse_id=wh3）
    - S3：province=P-S3 未配置服务仓 => FULFILLMENT_BLOCKED（reason=NO_SERVICE_PROVINCE）
    """
    session = db_session_like_pg

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    random.seed(2025_11_19)
    wh1, wh2, wh3 = await seed_world_phase5(session)

    # 使用测试基线里真实存在的 item_id，避免 FK 漂移
    item_ids = await _pick_existing_item_ids(session, n=3)

    shop_province = {"S1": "P-S1", "S2": "P-S2", "S3": "P-S3"}

    orders = generate_orders(200, item_ids=item_ids)
    for order in orders:
        province = shop_province[order.shop_id]
        await OrderService.ingest(
            session,
            platform=order.platform,
            shop_id=order.shop_id,
            ext_order_no=order.ext_order_id,
            items=[{"item_id": line.item_id, "qty": line.qty} for line in order.lines],
            address={"province": province, "receiver_name": "X", "receiver_phone": "000"},
        )

    await session.commit()

    summary = await collect_order_summary_phase5(session)

    print("\n=== Phase 5 Service Assignment Summary (Ingest Only) ===")
    for row in summary:
        print(row)

    # ----------------------
    # S1：应全部 SERVICE_ASSIGNED 到 wh2
    # ----------------------
    s1 = [r for r in summary if r.shop_id == "S1"]
    assert s1, "no S1 rows in summary"
    assert all(str(r.fulfillment_status) == "SERVICE_ASSIGNED" for r in s1)
    assert sum(int(r.n) for r in s1 if int(r.service_warehouse_id) == int(wh2)) > 0
    assert sum(int(r.n) for r in s1 if int(r.service_warehouse_id) not in (0, int(wh2))) == 0

    # ----------------------
    # S2：应全部 SERVICE_ASSIGNED 到 wh3
    # ----------------------
    s2 = [r for r in summary if r.shop_id == "S2"]
    assert s2, "no S2 rows in summary"
    assert all(str(r.fulfillment_status) == "SERVICE_ASSIGNED" for r in s2)
    assert sum(int(r.n) for r in s2 if int(r.service_warehouse_id) == int(wh3)) > 0
    assert sum(int(r.n) for r in s2 if int(r.service_warehouse_id) not in (0, int(wh3))) == 0

    # ----------------------
    # S3：应出现 FULFILLMENT_BLOCKED，且 service_warehouse_id=0
    # ----------------------
    s3 = [r for r in summary if r.shop_id == "S3"]
    assert s3, "no S3 rows in summary"
    blocked_s3 = sum(int(r.n) for r in s3 if str(r.fulfillment_status) == "FULFILLMENT_BLOCKED")
    assert blocked_s3 > 0
    assert sum(int(r.n) for r in s3 if int(r.service_warehouse_id) != 0) == 0
