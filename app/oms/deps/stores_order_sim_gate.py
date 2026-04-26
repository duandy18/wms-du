# app/oms/deps/stores_order_sim_gate.py
from __future__ import annotations

import os

from fastapi import HTTPException

from app.core.problem import make_problem


def _get_order_sim_test_store_id() -> int | None:
    raw = (os.getenv("ORDER_SIM_TEST_STORE_ID") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except Exception:
        return None


def enforce_order_sim_test_store_id_gate(*, store_id: int) -> None:
    tid = _get_order_sim_test_store_id()
    if tid is None:
        return

    if int(store_id) != int(tid):
        raise HTTPException(
            status_code=403,
            detail=make_problem(
                status_code=403,
                error_code="forbidden",
                message="order-sim 已启用测试店铺门禁：仅允许 TEST store_id 访问",
                context={"store_id": int(store_id), "allowed_test_store_id": int(tid)},
            ),
        )


def _get_order_sim_test_store_code() -> str | None:
    raw = (os.getenv("TEST_STORE_CODE") or "").strip()
    return raw or None


def enforce_order_sim_test_store_code_gate(*, store_code: str) -> None:
    tid = _get_order_sim_test_store_code()
    if tid is None:
        return

    if str(store_code) != tid:
        raise HTTPException(
            status_code=403,
            detail=make_problem(
                status_code=403,
                error_code="forbidden",
                message="order-sim 已启用测试店铺门禁：仅允许 TEST store_code 访问",
                context={
                    "store_code": str(store_code),
                    "allowed_test_store_code": str(tid),
                },
            ),
        )
