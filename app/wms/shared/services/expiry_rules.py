from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Optional


class ShelfLifeUnit(str, Enum):
    """
    保质期单位：
    - DAY   : 按天
    - MONTH : 按自然月（推荐，和包装“18个月”“24个月”一致）
    """

    DAY = "DAY"
    MONTH = "MONTH"


@dataclass(frozen=True)
class ShelfLife:
    """
    保质期配置：
    - value: 数值（>0）
    - unit : 单位（默认按月）
    """

    value: int
    unit: ShelfLifeUnit = ShelfLifeUnit.MONTH

    def is_effective(self) -> bool:
        """是否配置了有效保质期（>0）"""
        return self.value is not None and self.value > 0


def add_months(d: date, months: int) -> date:
    """
    按“自然月”增加月份，而不是简单 30 * N 天。

    规则：
    - 2025-01-15 + 1 月 -> 2025-02-15
    - 2025-01-31 + 1 月 -> 2025-02-28（取该月最后一天）
    - 2025-01-31 + 2 月 -> 2025-03-31
    """
    if months == 0:
        return d

    total_months = d.year * 12 + (d.month - 1) + months
    year = total_months // 12
    month = total_months % 12 + 1

    # 该月最后一天
    last_day = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day)

    return date(year, month, day)


def compute_expiry_from_shelf_life(
    production_date: date,
    shelf_life: ShelfLife,
) -> date:
    """
    根据“生产日期 + 保质期”计算到期日。

    语义约定：
    - 返回的 expiry_date 表示“最后一个合规日”（含当天）。
      即：today <= expiry_date 视为“未过期”，today > expiry_date 视为“已过期”。

    逻辑：
    - 如果单位是 DAY  ：expiry = production_date + value 天
    - 如果单位是 MONTH：expiry = production_date + value 个月（自然月规则）
    """
    if production_date is None:
        raise ValueError("production_date is required to compute expiry_date")

    if not shelf_life.is_effective():
        raise ValueError("shelf_life must be a positive value")

    if shelf_life.unit == ShelfLifeUnit.DAY:
        return production_date + timedelta(days=shelf_life.value)

    # 默认按月
    return add_months(production_date, shelf_life.value)


def resolve_expiry_date(
    *,
    production_date: Optional[date],
    expiry_date: Optional[date],
    shelf_life: Optional[ShelfLife],
) -> Optional[date]:
    """
    统一“到期日”解析规则（后续可在入库 / 盘点 / RMA 里复用）：

    优先级：
    1) 如果显式给了 expiry_date → 直接使用（例如包装上印的到期日）
    2) 否则，如果给了 production_date + 有效 shelf_life → 通过保质期推算
    3) 否则 → 返回 None（调用方可选择抛错或允许为空）

    备注：
    - 调用方可以在“入库 / 盘盈”等场景下强制要求结果非空；
    - FEFO 场景建议强制要求 expiry_date，不要允许 None。
    """
    if expiry_date is not None:
        return expiry_date

    if production_date is not None and shelf_life is not None and shelf_life.is_effective():
        return compute_expiry_from_shelf_life(production_date, shelf_life)

    return None


def validate_expiry_consistency(
    *,
    production_date: Optional[date],
    expiry_date: Optional[date],
    shelf_life: Optional[ShelfLife],
    tolerance_days: int = 3,
) -> bool:
    """
    可选的一致性校验（不是硬约束，更多用于诊断 / 报警）：

    - 如果给了 production_date + shelf_life，也给了 expiry_date，
      则检查 “通过保质期推算的日期” 与 “显式 expiry_date” 是否在
      ±tolerance_days 范围内（默认 3 天）；

    - 用于发现：商品档案里的保质期配置、包装上印刷的到期日是否明显不一致。

    返回：
    - True  : 看起来一致或无法判断
    - False : 明显不一致（可记录 warning / audit）
    """
    if (
        production_date is None
        or expiry_date is None
        or shelf_life is None
        or not shelf_life.is_effective()
    ):
        # 信息不全，无法校验，当作“没发现问题”
        return True

    expected = compute_expiry_from_shelf_life(production_date, shelf_life)
    delta_days = abs((expiry_date - expected).days)
    return delta_days <= max(tolerance_days, 0)
