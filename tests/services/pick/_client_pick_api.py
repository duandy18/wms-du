# tests/services/pick/_client_pick_api.py
from __future__ import annotations

from typing import Any, Dict, Optional


async def scan_pick(
    client_like,
    *,
    task_id: int,
    item_id: int,
    qty: int,
    batch_code: Optional[str] = None,
) -> dict:
    payload: Dict[str, Any] = {"item_id": int(item_id), "qty": int(qty)}
    if batch_code is not None:
        payload["batch_code"] = str(batch_code)
    resp = await client_like.post(f"/pick-tasks/{int(task_id)}/scan", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def create_pick_task_from_order(client_like, *, warehouse_id: int, order_id: int) -> dict:
    resp = await client_like.post(
        f"/pick-tasks/from-order/{int(order_id)}",
        json={"warehouse_id": int(warehouse_id), "source": "ORDER", "priority": 100},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def get_pick_task(client_like, *, task_id: int) -> dict:
    resp = await client_like.get(f"/pick-tasks/{int(task_id)}")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def commit_pick_task(
    client_like,
    *,
    task_id: int,
    platform: str,
    shop_id: str,
    trace_id: Optional[str] = None,
    allow_diff: bool = True,
):
    payload: Dict[str, Any] = {
        "platform": str(platform).upper(),
        "shop_id": str(shop_id),
        "allow_diff": bool(allow_diff),
    }
    if trace_id:
        payload["trace_id"] = str(trace_id)

    resp = await client_like.post(f"/pick-tasks/{int(task_id)}/commit", json=payload)
    return resp
