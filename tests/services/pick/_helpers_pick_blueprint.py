# tests/services/pick/_helpers_pick_blueprint.py
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

PICK_TASKS_PREFIX = "/pick-tasks"
WAREHOUSE_ID = 1

PLATFORM = "pdd"
SHOP_ID = "1"


# -----------------------------
# DB helpers (transaction view)
# -----------------------------
async def _ensure_fresh_read_view(session: AsyncSession) -> None:
    """
    只在“没有 pending writes”的情况下 rollback，释放事务快照，
    以便读取到 HTTP API 侧（其它连接）提交的最新数据。
    """
    if not session.in_transaction():
        return

    has_pending_writes = bool(
        getattr(session, "new", None) or getattr(session, "dirty", None) or getattr(session, "deleted", None)
    )
    if has_pending_writes:
        return

    await session.rollback()


async def ledger_count(session: AsyncSession) -> int:
    await _ensure_fresh_read_view(session)
    r = await session.execute(text("SELECT COUNT(*) FROM stock_ledger"))
    return int((r.first() or (0,))[0] or 0)


async def stocks_count(session: AsyncSession) -> int:
    await _ensure_fresh_read_view(session)
    r = await session.execute(text("SELECT COUNT(*) FROM stocks"))
    return int((r.first() or (0,))[0] or 0)


async def pick_any_item_id(session: AsyncSession) -> int:
    await _ensure_fresh_read_view(session)
    r = await session.execute(text("SELECT id FROM items ORDER BY id ASC LIMIT 1"))
    row = r.first()
    if not row:
        raise AssertionError("items 表为空：无法构造蓝皮书 Pick 测试订单（请确保 seed 有 items）")
    return int(row[0])


async def columns_of(session: AsyncSession, table_name: str) -> List[Tuple[str, bool, Optional[str], str]]:
    await _ensure_fresh_read_view(session)
    r = await session.execute(
        text(
            """
            SELECT column_name,
                   (is_nullable = 'YES') AS is_nullable,
                   column_default,
                   data_type
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = :t
             ORDER BY ordinal_position
            """
        ),
        {"t": table_name},
    )
    rows = r.fetchall()
    out: List[Tuple[str, bool, Optional[str], str]] = []
    for name, is_nullable, default, data_type in rows:
        out.append(
            (
                str(name),
                bool(is_nullable),
                default if default is None else str(default),
                str(data_type),
            )
        )
    return out


# -----------------------------
# Minimal order seeding helpers
# -----------------------------
async def insert_min_order(session: AsyncSession, *, warehouse_id: int) -> int:
    ext = f"UT-PICK-BLUEPRINT-{uuid.uuid4().hex[:10]}"
    r = await session.execute(
        text(
            """
            INSERT INTO orders (platform, shop_id, ext_order_no, warehouse_id, fulfillment_status, status)
            VALUES (:p, :s, :ext, :wid, :fs, :st)
            RETURNING id
            """
        ),
        {
            "p": PLATFORM,
            "s": SHOP_ID,
            "ext": ext,
            "wid": int(warehouse_id),
            # 执行态：让订单可进入仓内执行（以你当前主线状态机为准）
            "fs": "READY_TO_FULFILL",
            "st": "CREATED",
        },
    )
    row = r.first()
    if not row:
        raise AssertionError("failed to insert orders row")
    return int(row[0])


async def insert_one_order_item(session: AsyncSession, *, order_id: int, item_id: int, qty: int) -> int:
    cols = await columns_of(session, "order_items")
    col_names = {c[0] for c in cols}
    col_types = {c[0]: c[3] for c in cols}

    data: Dict[str, Any] = {
        "order_id": int(order_id),
        "item_id": int(item_id),
        "qty": int(qty),
    }

    # 统一把“执行事实字段”归零（不包含旧预占语义字段）
    zero_int_fields = [
        "shipped_qty",
        "picked_qty",
        "allocated_qty",
        "packed_qty",
        "packaged_qty",
        "canceled_qty",
        "cancelled_qty",
        "refunded_qty",
        "returned_qty",
    ]
    for k in zero_int_fields:
        if k in col_names:
            data[k] = 0

    zero_num_fields = [
        "price",
        "discount",
        "amount",
        "cost",
        "cost_estimated",
        "cost_real",
    ]
    for k in zero_num_fields:
        if k in col_names and k not in data:
            data[k] = 0

    json_fields: List[str] = [name for name, _n, _d, dtype in cols if dtype in ("json", "jsonb")]

    if "meta" in col_names and "meta" not in data:
        data["meta"] = {}
    if "extras" in col_names and "extras" not in data:
        data["extras"] = {}

    for k in list(data.keys()):
        if k in json_fields and isinstance(data[k], (dict, list)):
            data[k] = json.dumps(data[k], ensure_ascii=False)

    insert_cols = list(data.keys())
    value_exprs: List[str] = []
    for k in insert_cols:
        dtype = col_types.get(k, "")
        if dtype == "jsonb":
            value_exprs.append(f"CAST(:{k} AS JSONB)")
        elif dtype == "json":
            value_exprs.append(f"CAST(:{k} AS JSON)")
        else:
            value_exprs.append(f":{k}")

    sql = f"""
        INSERT INTO order_items ({", ".join(insert_cols)})
        VALUES ({", ".join(value_exprs)})
        RETURNING id
    """

    r = await session.execute(text(sql), data)
    row = r.first()
    if not row:
        raise AssertionError("failed to insert order_items row")
    return int(row[0])


async def ensure_pickable_order(session: AsyncSession, *, warehouse_id: int = WAREHOUSE_ID) -> int:
    """
    两段提交，避免任何 rollback/快照刷新误伤 FK：
      1) orders -> commit
      2) order_items -> commit
    """
    item_id = await pick_any_item_id(session)

    order_id = await insert_min_order(session, warehouse_id=warehouse_id)
    await session.commit()

    _ = await insert_one_order_item(session, order_id=order_id, item_id=item_id, qty=1)
    await session.commit()

    return order_id


# -----------------------------
# API helpers (names must match test imports)
# -----------------------------
async def create_pick_task_from_order(client_like, *, warehouse_id: int, order_id: int) -> Dict[str, Any]:
    r = await client_like.post(
        f"{PICK_TASKS_PREFIX}/from-order/{order_id}",
        json={"warehouse_id": warehouse_id, "source": "ORDER", "priority": 10},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, dict)
    assert int(body.get("id") or 0) > 0
    return body


async def get_pick_task(client_like, *, task_id: int) -> Dict[str, Any]:
    r = await client_like.get(f"{PICK_TASKS_PREFIX}/{task_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, dict)
    return body


def get_task_ref(task: Dict[str, Any]) -> str:
    ref = str(task.get("ref") or "").strip()
    if ref:
        return ref
    return f"PICKTASK:{int(task['id'])}"


def build_handoff_code(ref: str) -> str:
    s = str(ref or "").strip()
    if s.startswith("ORD:"):
        parts = s.split(":", 3)
        if len(parts) == 4:
            _, plat, shop, ext = parts
            return f"WMS:ORDER:v1:{plat}:{shop}:{ext}"
    return s


async def scan_pick(
    client_like,
    *,
    task_id: int,
    item_id: int,
    qty: int,
    batch_code: Optional[str],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"item_id": int(item_id), "qty": int(qty)}
    if batch_code is not None:
        payload["batch_code"] = batch_code
    r = await client_like.post(f"{PICK_TASKS_PREFIX}/{task_id}/scan", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, dict)
    return body


async def commit_pick_task(
    client_like,
    *,
    task_id: int,
    platform: str,
    shop_id: str,
    handoff_code: str,
    trace_id: str,
    allow_diff: bool,
):
    r = await client_like.post(
        f"{PICK_TASKS_PREFIX}/{task_id}/commit",
        json={
            "platform": platform,
            "shop_id": shop_id,
            "handoff_code": handoff_code,
            "trace_id": trace_id,
            "allow_diff": allow_diff,
        },
    )
    return r


async def force_no_stock(session: AsyncSession, *, warehouse_id: int, item_id: int) -> None:
    await _ensure_fresh_read_view(session)
    await session.execute(
        text("DELETE FROM stocks WHERE warehouse_id = :w AND item_id = :i"),
        {"w": int(warehouse_id), "i": int(item_id)},
    )
    await session.commit()


__all__ = [
    "PICK_TASKS_PREFIX",
    "WAREHOUSE_ID",
    "PLATFORM",
    "SHOP_ID",
    "ledger_count",
    "stocks_count",
    "pick_any_item_id",
    "ensure_pickable_order",
    "create_pick_task_from_order",
    "get_pick_task",
    "get_task_ref",
    "build_handoff_code",
    "scan_pick",
    "commit_pick_task",
    "force_no_stock",
]
