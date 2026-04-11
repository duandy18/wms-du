from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.pms.public.items.services.item_read_service import ItemReadService
from app.wms.shared.services.expiry_rules import (
    ShelfLife,
    ShelfLifeUnit,
    resolve_expiry_date,
    resolve_production_date,
    validate_expiry_consistency,
)


class BatchDateResolutionMode(str, Enum):
    FROM_PRODUCTION_AND_SHELF_LIFE = "FROM_PRODUCTION_AND_SHELF_LIFE"
    FROM_BOTH_EXPLICIT = "FROM_BOTH_EXPLICIT"
    FROM_EXPIRY_AND_SHELF_LIFE_REVERSE = "FROM_EXPIRY_AND_SHELF_LIFE_REVERSE"


def _coerce_date_like(v: object, *, field_name: str) -> Optional[date]:
    if v is None:
        return None

    if isinstance(v, datetime):
        return v.date()

    if isinstance(v, date):
        return v

    s = str(v).strip()
    if not s:
        return None

    try:
        return date.fromisoformat(s)
    except ValueError:
        pass

    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError as e:
        raise ValueError(f"{field_name} must be a valid ISO date/datetime string") from e


def _build_shelf_life(*, value: object, unit_str: object) -> Optional[ShelfLife]:
    if value is None or unit_str is None:
        return None

    try:
        v = int(value)
    except (TypeError, ValueError):
        return None

    if v <= 0:
        return None

    try:
        unit = ShelfLifeUnit(str(unit_str))
    except ValueError:
        # 保底按 DAY 处理脏数据，避免直接 500
        unit = ShelfLifeUnit.DAY

    shelf_life = ShelfLife(value=v, unit=unit)
    return shelf_life if shelf_life.is_effective() else None


async def normalize_batch_dates_for_item(
    session: AsyncSession,
    *,
    item_id: int,
    production_date: Optional[date | datetime | str],
    expiry_date: Optional[date | datetime | str],
) -> tuple[Optional[date], Optional[date], Optional[BatchDateResolutionMode]]:
    """
    统一“批次日期归一”逻辑：

    输入：
    - item_id          : 商品 ID（用于读取 expiry_policy / shelf_life / derivation_allowed）
    - production_date  : 生产日期（可空；支持 date / datetime / ISO string）
    - expiry_date      : 到期日期（可空；支持 date / datetime / ISO string）

    输出：
    - resolved_production_date
    - resolved_expiry_date
    - resolution_mode（成功归一时给出；若无法归一则为 None）

    规则：
    1) expiry_policy=NONE：
       - 统一归一为 (None, None, None)
    2) 两者都给：
       - 直接保留
       - 若 production_date > expiry_date，则报错
       - 若存在有效 shelf_life，可做轻量一致性校验（当前先不硬拦）
    3) 只给 production_date：
       - 若 derivation_allowed + shelf_life 有效，则正推 expiry_date
       - 否则返回 (production_date, None, None)
    4) 只给 expiry_date：
       - 若 derivation_allowed + shelf_life 有效，则反推 production_date
       - 否则返回 (None, expiry_date, None)
    5) 两者都空：
       - 返回 (None, None, None)

    注意：
    - 这里不做“结果必须非空”的硬校验；是否允许 unresolved，交给调用方场景判断
    - 当前 lot identity 仍依赖 production_date，因此 REQUIRED 路径若最终 resolved_production_date 仍为空，
      应由调用方或后续 lot 解析层报错
    """
    production_date = _coerce_date_like(production_date, field_name="production_date")
    expiry_date = _coerce_date_like(expiry_date, field_name="expiry_date")

    # 两者都空：直接返回
    if production_date is None and expiry_date is None:
        return None, None, None

    svc = ItemReadService(session)
    policy = await svc.aget_policy_by_id(item_id=int(item_id))
    if policy is None:
        # 未找到 item：保守返回原值，不在共享层擅自抛错
        if production_date is not None and expiry_date is not None:
            if production_date > expiry_date:
                raise ValueError("production_date cannot be later than expiry_date")
            return production_date, expiry_date, BatchDateResolutionMode.FROM_BOTH_EXPLICIT
        return production_date, expiry_date, None

    expiry_policy = str(getattr(policy, "expiry_policy", "NONE") or "NONE").upper()
    derivation_allowed = bool(getattr(policy, "derivation_allowed", True))
    shelf_life = _build_shelf_life(
        value=getattr(policy, "shelf_life_value", None),
        unit_str=getattr(policy, "shelf_life_unit", None),
    )

    # NONE 商品：统一不承载日期
    if expiry_policy == "NONE":
        return None, None, None

    # 两者都给：保留显式值
    if production_date is not None and expiry_date is not None:
        if production_date > expiry_date:
            raise ValueError("production_date cannot be later than expiry_date")

        # 当前先做轻量一致性检查；不在共享层硬拦
        _ = validate_expiry_consistency(
            production_date=production_date,
            expiry_date=expiry_date,
            shelf_life=shelf_life,
        )
        return production_date, expiry_date, BatchDateResolutionMode.FROM_BOTH_EXPLICIT

    # 只给生产日期：正推 expiry_date
    if production_date is not None and expiry_date is None:
        if derivation_allowed and shelf_life is not None:
            resolved_expiry = resolve_expiry_date(
                production_date=production_date,
                expiry_date=None,
                shelf_life=shelf_life,
            )
            return production_date, resolved_expiry, BatchDateResolutionMode.FROM_PRODUCTION_AND_SHELF_LIFE

        return production_date, None, None

    # 只给到期日期：反推 production_date
    if production_date is None and expiry_date is not None:
        if derivation_allowed and shelf_life is not None:
            resolved_production = resolve_production_date(
                production_date=None,
                expiry_date=expiry_date,
                shelf_life=shelf_life,
            )
            return resolved_production, expiry_date, BatchDateResolutionMode.FROM_EXPIRY_AND_SHELF_LIFE_REVERSE

        return None, expiry_date, None

    return production_date, expiry_date, None
