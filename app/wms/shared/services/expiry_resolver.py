from __future__ import annotations

from datetime import date
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.pms.public.items.services.item_read_service import ItemReadService
from app.wms.shared.services.expiry_rules import ShelfLife, ShelfLifeUnit, resolve_expiry_date


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
         - 从 PMS public policy 读取 expiry_policy / shelf_life
         - 若 expiry_policy=REQUIRED 且存在有效保质期 → 通过 expiry_rules 计算 expiry_date
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

    svc = ItemReadService(session)
    policy = await svc.aget_policy_by_id(item_id=int(item_id))
    if policy is None:
        # 未找到 item，直接返回原值，后续由调用方决定是否抛错
        return production_date, None

    if policy.expiry_policy == "NONE":
        # 明确无效期策略：不推算
        return production_date, None

    value = policy.shelf_life_value
    unit_str = policy.shelf_life_unit
    if value is None or value <= 0 or unit_str is None:
        # 没配置完整保质期，无法推断
        return production_date, None

    # 解析单位字符串；异常时保底按 DAY 处理，避免脏数据引发 500
    try:
        unit = ShelfLifeUnit(unit_str or "DAY")
    except ValueError:
        unit = ShelfLifeUnit.DAY

    shelf_life = ShelfLife(value=int(value), unit=unit)

    computed = resolve_expiry_date(
        production_date=production_date,
        expiry_date=None,
        shelf_life=shelf_life,
    )
    return production_date, computed
