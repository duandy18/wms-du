# app/tms/quote/context.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class QuoteGroupMemberContext:
    id: int
    province_code: Optional[str]
    province_name: Optional[str]


@dataclass
class QuoteMatrixRowContext:
    id: int
    group_id: int
    module_range_id: int
    pricing_mode: str
    flat_amount: Optional[float]
    base_amount: Optional[float]
    rate_per_kg: Optional[float]
    base_kg: Optional[float]
    active: bool
    min_kg: float
    max_kg: Optional[float]


@dataclass
class QuoteGroupContext:
    id: int
    name: str
    active: bool
    members: list[QuoteGroupMemberContext]


@dataclass
class QuoteSurchargeCityContext:
    id: int
    city_code: Optional[str]
    city_name: Optional[str]
    fixed_amount: float
    active: bool


@dataclass
class QuoteSurchargeConfigContext:
    id: int
    province_code: Optional[str]
    province_name: Optional[str]
    province_mode: str
    fixed_amount: float
    active: bool
    cities: list[QuoteSurchargeCityContext]


@dataclass
class QuoteCalcContext:
    template_id: int
    shipping_provider_id: int
    shipping_provider_name: Optional[str]
    template_name: str

    status: str
    archived_at: Optional[datetime]

    # 当前终态合同下，模板主表不再保存旧平铺计费规则；
    # quote 侧使用运行期默认值。
    currency: str
    billable_weight_strategy: str
    volume_divisor: Optional[int]
    rounding_mode: str
    rounding_step_kg: Optional[float]
    min_billable_weight_kg: Optional[float]

    groups: list[QuoteGroupContext]
    matrix_rows: list[QuoteMatrixRowContext]
    surcharge_configs: list[QuoteSurchargeConfigContext]
