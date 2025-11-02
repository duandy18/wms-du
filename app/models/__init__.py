# app/models/__init__.py
"""
聚合 ORM 基类，并在导入时安全地加载所有模型模块，
确保 SQLAlchemy 的关系映射（relationship("...")）能正确注册。

用途：
- 测试或服务代码在未 import app.main 的情况下，也能直接使用 ORM。
- 某些模块缺失时不会阻断（try/except 保护），便于渐进迁移。
"""

from __future__ import annotations

from app.db.base import Base  # 声明式基类


def _safe_import(module_path: str) -> None:
    """安全导入模型模块：不存在时跳过，不影响整体导入。"""
    try:
        __import__(module_path)
    except Exception:
        # 不打印噪音日志：测试/子集运行时允许部分模型缺席
        pass


def _import_all_models() -> None:
    """
    将项目里的模型模块尽量全部导入到同一个 registry，
    解决 relationship("OrderItem") 这类字符串引用在首次使用时未解析的问题。
    """
    # 维表/主数据
    _safe_import("app.models.item")
    _safe_import("app.models.location")
    _safe_import("app.models.warehouse")
    _safe_import("app.models.party")
    _safe_import("app.models.store")
    _safe_import("app.models.platform_shops")

    # 交易/单据
    _safe_import("app.models.order")
    _safe_import("app.models.order_item")
    _safe_import("app.models.return_record")

    # 库存相关
    _safe_import("app.models.stock")
    _safe_import("app.models.batch")
    _safe_import("app.models.stock_ledger")
    _safe_import("app.models.stock_snapshot")
    _safe_import("app.models.inventory")

    # 权限/用户
    _safe_import("app.models.user")
    _safe_import("app.models.role")
    _safe_import("app.models.permission")
    _safe_import("app.models.role_grants")
    _safe_import("app.models.associations")

    # 事件/日志
    _safe_import("app.models.event_error_log")


# 在导入 app.models 时立即完成注册
_import_all_models()

__all__ = ["Base"]
