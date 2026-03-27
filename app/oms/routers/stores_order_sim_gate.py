# app/api/routers/stores_routes_order_sim_gate.py
from __future__ import annotations

import os

from fastapi import HTTPException

from app.api.problem import make_problem


def _get_order_sim_test_store_id() -> int | None:
    raw = (os.getenv("ORDER_SIM_TEST_STORE_ID") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except Exception:
        return None


def enforce_order_sim_test_store_gate(*, store_id: int) -> None:
    tid = _get_order_sim_test_store_id()
    if tid is None:
        return
    if int(store_id) != int(tid):
        raise HTTPException(
            status_code=403,
            detail=make_problem(
                status_code=403,
                error_code="forbidden",
                message="order-sim 已启用测试商铺门禁：仅允许 TEST store_id 访问",
                context={"store_id": int(store_id), "allowed_test_store_id": int(tid)},
            ),
        )


def _get_test_shop_id() -> str | None:
    s = (os.getenv("TEST_SHOP_ID") or "").strip()
    return s or None


def enforce_order_sim_test_shop_gate(*, shop_id: str) -> None:
    """
    可选：当 TEST_SHOP_ID 设置后，order-sim 入口只能用于该测试商铺。
    """
    tid = _get_test_shop_id()
    if tid is None:
        return
    if str(shop_id) != tid:
        raise HTTPException(
            status_code=403,
            detail=make_problem(
                status_code=403,
                error_code="forbidden",
                message="order-sim 已启用测试商铺门禁：仅允许 TEST shop_id 访问",
                context={"shop_id": str(shop_id), "allowed_test_shop_id": str(tid)},
            ),
        )
