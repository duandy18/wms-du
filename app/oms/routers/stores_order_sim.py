# app/oms/routers/stores_order_sim.py
from __future__ import annotations

from fastapi import APIRouter

from app.oms.routers import stores_order_sim_cart
from app.oms.routers import stores_order_sim_generate
from app.oms.routers import stores_order_sim_merchant_lines


def register(router: APIRouter) -> None:
    """
    order-sim 路由聚合器（薄门面）：
    - merchant-lines + filled-code-options
    - cart
    - preview-order / generate-order

    ✅ 所有门禁/护栏/写路径逻辑均已下沉到子模块，避免本文件膨胀。
    """
    stores_order_sim_merchant_lines.register(router)
    stores_order_sim_cart.register(router)
    stores_order_sim_generate.register(router)
