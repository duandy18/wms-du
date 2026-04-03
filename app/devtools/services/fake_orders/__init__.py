# app/devtools/services/fake_orders/__init__.py
from __future__ import annotations

from app.devtools.services.fake_orders.generate import generate_orders, make_ext_order_no
from app.devtools.services.fake_orders.report import build_report
from app.devtools.services.fake_orders.seed import parse_seed
from app.devtools.services.fake_orders.types import FakeLink, FakeSeed, FakeShopSeed, FakeVariant

__all__ = [
    "FakeVariant",
    "FakeLink",
    "FakeShopSeed",
    "FakeSeed",
    "parse_seed",
    "make_ext_order_no",
    "generate_orders",
    "build_report",
]
