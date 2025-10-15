# app/db/base.py
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """项目统一的 Declarative Base。"""

    pass


def _import_all_models() -> None:
    """
    集中导入所有 ORM 模型，确保它们被注册进 Base.metadata。
    Alembic 的 autogenerate 依赖于这些 import。
    """
    modules = [
        "app.models.item",
        "app.models.warehouse",
        "app.models.location",
        "app.models.stock",
        "app.models.batch",  # 关键：批次模型
        "app.models.stock_ledger",  # 关键：台账模型
        # 如有其它模块（orders、suppliers 等），按需继续补充
    ]
    for m in modules:
        try:
            __import__(m)
        except Exception:
            # 允许模型在个别环境（如本地极简运行）缺失，不阻塞 Alembic
            pass


# 模块 import 放在文件末尾，以避免循环导入
_import_all_models()

__all__ = ["Base"]
