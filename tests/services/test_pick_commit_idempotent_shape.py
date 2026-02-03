# tests/services/test_pick_commit_idempotent_shape.py
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.services.pick._helpers_pick_blueprint import (
    PLATFORM,
    SHOP_ID,
    WAREHOUSE_ID,
    build_handoff_code,
    commit_pick_task,
    create_pick_task_from_order,
    ensure_pickable_order,
    get_task_ref,
    pick_any_item_id,
    scan_pick,
)


def _assert_commit_ok_shape(x: dict) -> None:
    assert isinstance(x, dict)

    # 顶层字段存在性（同形状护栏）
    for k in (
        "status",
        "idempotent",
        "task_id",
        "warehouse_id",
        "platform",
        "shop_id",
        "ref",
        "trace_id",
        "committed_at",
        "diff",
    ):
        assert k in x, f"missing field: {k}"

    assert x["status"] == "OK"
    assert isinstance(x["idempotent"], bool)
    assert isinstance(x["task_id"], int)
    assert isinstance(x["warehouse_id"], int)
    assert isinstance(x["platform"], str) and x["platform"]
    assert isinstance(x["shop_id"], str)
    assert isinstance(x["ref"], str) and x["ref"]
    assert isinstance(x["trace_id"], str) and x["trace_id"]
    assert isinstance(x["committed_at"], str) and x["committed_at"]

    d = x["diff"]
    assert isinstance(d, dict)
    for k in ("task_id", "has_over", "has_under", "has_temp_lines", "temp_lines_n", "lines"):
        assert k in d, f"missing diff field: {k}"
    assert isinstance(d["task_id"], int)
    assert isinstance(d["has_over"], bool)
    assert isinstance(d["has_under"], bool)
    assert isinstance(d["has_temp_lines"], bool)
    assert isinstance(d["temp_lines_n"], int)
    assert isinstance(d["lines"], list)


@pytest.mark.asyncio
async def test_pick_commit_idempotent_shape(client, session: AsyncSession):
    """
    最小合同测试（启用版）：
    - 用蓝皮书 helper 创建可 pickable 的订单
    - 创建 pick_task（from-order/{order_id}）
    - scan 写入事实
    - commit 两次：第二次必须幂等短路
    - 断言响应字段集合一致（同形状）
    """
    # 1) 确保有可用 item，并构造一笔可 pickable 订单（order_id 是 orders.id）
    item_id = await pick_any_item_id(session)
    order_id = await ensure_pickable_order(session, warehouse_id=WAREHOUSE_ID)

    # 2) 创建 pick_task
    task = await create_pick_task_from_order(client, warehouse_id=WAREHOUSE_ID, order_id=order_id)
    task_id = int(task["id"])
    order_ref = get_task_ref(task)
    handoff_code = build_handoff_code(order_ref)

    # 3) 录入 scan 事实（batch_code 允许为 None；后端会按 has_shelf_life 合同处理）
    _ = await scan_pick(client, task_id=task_id, item_id=item_id, qty=1, batch_code=None)

    # 4) commit 两次
    r1 = await commit_pick_task(
        client,
        task_id=task_id,
        platform=str(PLATFORM).upper(),
        shop_id=str(SHOP_ID),
        handoff_code=handoff_code,
        trace_id=str(order_ref),
        allow_diff=True,
    )
    assert r1.status_code == 200, r1.text
    a = r1.json()
    _assert_commit_ok_shape(a)
    assert a["idempotent"] is False

    r2 = await commit_pick_task(
        client,
        task_id=task_id,
        platform=str(PLATFORM).upper(),
        shop_id=str(SHOP_ID),
        handoff_code=handoff_code,
        trace_id=str(order_ref),
        allow_diff=True,
    )
    assert r2.status_code == 200, r2.text
    b = r2.json()
    _assert_commit_ok_shape(b)
    assert b["idempotent"] is True

    # 5) 同形状：字段集合一致（顶层 + diff）
    assert set(a.keys()) == set(b.keys())
    assert set(a["diff"].keys()) == set(b["diff"].keys())
