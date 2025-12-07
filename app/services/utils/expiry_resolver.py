from __future__ import annotations

from datetime import date
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.services.utils.expiry_rules import ShelfLife, ShelfLifeUnit, resolve_expiry_date


async def resolve_batch_dates_for_item(
    session: AsyncSession,
    *,
    item_id: int,
    production_date: Optional[date],
    expiry_date: Optional[date],
) -> Tuple[Optional[date], Optional[date]]:
    """
    统一“批次日期解析”逻辑：

    输入：
    - item_id          : 商品 ID（用于读取保质期配置）
    - production_date  : 生产日期（可空）
    - expiry_date      : 到期日期（可空）

    规则：
    1) 如果显式给了 expiry_date → 直接使用（不动）
    2) 若未给 expiry_date 且有 production_date：
         - 从 items 读取 (shelf_life_value, shelf_life_unit)
         - 若存在有效保质期 → 通过 expiry_rules 计算 expiry_date
    3) 若两者皆无或无保质期配置 → 如实返回（可能都是 None）

    注意：
    - 不做硬校验；是否允许 None 由调用方根据场景决定（入库/盘盈可以强制）
    - 只读，不会修改数据库
    """
    # 显式给了到期日：尊重调用方
    if expiry_date is not None:
        return production_date, expiry_date

    # 没有生产日期就没法推算
    if production_date is None:
        return None, None

    # 读取 item 的保质期配置
    row = await session.execute(
        select(Item.shelf_life_value, Item.shelf_life_unit).where(Item.id == item_id)
    )
    res = row.one_or_none()
    if res is None:
        # 未找到 item，直接返回原值，后续由调用方决定是否抛错
        return production_date, None

    value, unit_str = res
    if value is None or value <= 0:
        # 没配置保质期，无法推断
        return production_date, None

    # 解析单位字符串；异常时保底按 DAY 处理，避免脏数据引发 500
    try:
        unit = ShelfLifeUnit(unit_str or "DAY")
    except ValueError:
        unit = ShelfLifeUnit.DAY

    shelf_life = ShelfLife(value=value, unit=unit)

    computed = resolve_expiry_date(
        production_date=production_date,
        expiry_date=None,
        shelf_life=shelf_life,
    )
    return production_date, computed
