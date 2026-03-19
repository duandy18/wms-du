# app/tms/pricing/contracts.py
# 分拆说明：
# - 本文件承载 TMS / Pricing（运价管理页）聚合视图合同；
# - 数据来自 provider / warehouse_binding / pricing_scheme 聚合；
# - 一行代表：网点 × 仓库 的当前运价状态（运行态视图）。
# - 当前页只做运营总览，不承担写入。

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


PricingStatus = Literal[
    "provider_disabled",
    "binding_disabled",
    "no_active_scheme",
    "ready",
]


class PricingListRow(BaseModel):
    provider_id: int
    provider_code: str
    provider_name: str
    provider_active: bool

    warehouse_id: int
    warehouse_name: str

    binding_active: bool

    active_scheme_id: int | None = None
    active_scheme_name: str | None = None
    active_scheme_status: str | None = None

    pricing_status: PricingStatus


class PricingListResponse(BaseModel):
    ok: bool = True
    rows: list[PricingListRow]
