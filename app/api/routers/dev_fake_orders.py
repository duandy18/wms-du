# app/api/routers/dev_fake_orders.py
from __future__ import annotations

# 兼容旧入口路径：main.py / 其他模块可能仍 import 这个文件的 router
from app.api.routers.dev_fake_orders_routes import router  # noqa: F401
