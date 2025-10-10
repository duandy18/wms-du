# app/db/base.py
from __future__ import annotations

from sqlalchemy.orm import declarative_base

Base = declarative_base()


# —— 重要：在此集中 import 所有模型，确保其被注册到 Base.metadata —— #
# 如果个别模型当前不存在也无妨，try/except 跳过即可（方便渐进开发）
def _import_all_models():
    modules = [
        "app.models.item",
        "app.models.order",
        "app.models.order_item",
        "app.models.warehouse",
        "app.models.location",
        "app.models.stock",
        # 如有其它：supplier、batch、movement……加在这里
    ]
    for m in modules:
        try:
            __import__(m)
        except Exception:
            # 开发期容忍未完成模块
            pass


_import_all_models()
