# app/schemas/__init__.py
"""
Schemas package (v1.0)

本包保持“安静”：
- 不做聚合导出，避免隐式导入引发的循环依赖与冷启动性能问题。
- 需要使用时请**显式**从具体模块导入，例如：
    from app.schemas.user import UserOut
    from app.schemas.order import OrderCreate, OrderOut
    from app.schemas.stock import StockAdjustIn, StockQueryOut
"""

# 仅提供包级元数据；不自动导出任何模型
__all__: list[str] = []

# 版本号用于调试与文档
__schema_version__ = "1.0.0"

# 你也可以在此放置轻量级的公共别名或常量（若未来有强需求再添加）
# 例如：
# from typing import Annotated  # noqa: F401
# 但默认不做任何导出，保持最小面。
