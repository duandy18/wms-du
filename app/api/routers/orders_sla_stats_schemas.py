# app/api/routers/orders_sla_stats_schemas.py
from __future__ import annotations

from pydantic import BaseModel, Field


class OrdersSlaStatsModel(BaseModel):
    """
    发货 SLA 统计：

    - total_orders    : 时间窗口内有发货记录的订单数
    - avg_ship_hours  : 平均发货耗时（小时）
    - p95_ship_hours  : 95 分位发货耗时（小时）
    - on_time_orders  : 在 SLA 小时内发货的订单数
    - on_time_rate    : 准时率 = on_time_orders / total_orders
    """

    total_orders: int = Field(..., description="时间窗口内有发货记录的订单数量")
    avg_ship_hours: float | None = Field(
        None,
        description="平均发货耗时（小时），无订单时为 null",
    )
    p95_ship_hours: float | None = Field(
        None,
        description="95 分位发货耗时（小时），无订单时为 null",
    )
    on_time_orders: int = Field(..., description="在 SLA 小时内发货的订单数")
    on_time_rate: float = Field(
        ...,
        description="准时率 = on_time_orders / total_orders（无订单时为 0.0）",
    )
