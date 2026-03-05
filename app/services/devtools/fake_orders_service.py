# app/services/devtools/fake_orders_service.py
from __future__ import annotations

# 兼容旧 import 路径：历史代码可能仍从 fake_orders_service import parse_seed/generate_orders/build_report
from app.services.devtools.fake_orders import (  # noqa: F401
    FakeLink,
    FakeSeed,
    FakeShopSeed,
    FakeVariant,
    build_report,
    generate_orders,
    make_ext_order_no,
    parse_seed,
)
