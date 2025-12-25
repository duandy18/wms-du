# app/api/routers/orders_stats_schemas.py
from __future__ import annotations

from datetime import date as _date
from typing import List, Optional

from pydantic import BaseModel, Field


class OrdersDailyStatsModel(BaseModel):
    """单日汇总：创建 / 发货 / 退货 订单数"""

    # 注意：类型用 _date，字段名仍然叫 date，避免和 datetime.date 类型同名
    date: _date = Field(..., description="统计日期（UTC，自然日）")
    platform: Optional[str] = Field(
        None,
        description="可选平台过滤（如 PDD），大写",
    )
    shop_id: Optional[str] = Field(
        None,
        description="可选店铺过滤（字符串，与 orders.shop_id 一致）",
    )
    orders_created: int = Field(..., description="当天创建的订单数量")
    orders_shipped: int = Field(
        ..., description="当天发货的订单数量（按 ref=ORD:* 的 distinct ref 计）"
    )
    orders_returned: int = Field(
        ..., description="当天有退货入库的订单数量（source_type=ORDER 的收货任务）"
    )


class OrdersDailyTrendItem(BaseModel):
    date: _date
    orders_created: int
    orders_shipped: int
    orders_returned: int
    return_rate: float = Field(
        ...,
        description="退货率 = orders_returned / orders_shipped（若分母为 0 则为 0.0）",
    )


class OrdersTrendResponseModel(BaseModel):
    days: List[OrdersDailyTrendItem] = Field(
        default_factory=list,
        description="按日期升序排列的 7 天趋势",
    )
