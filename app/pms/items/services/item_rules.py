# app/pms/items/services/item_rules.py
from __future__ import annotations

from app.models.item import Item

NOEXP_BATCH_CODE = "NOEXP"


def _is_required_expiry_policy(v: object) -> bool:
    return str(v or "").strip().upper() == "REQUIRED"


def decorate_rules(obj: Item) -> Item:
    """
    给 Item 注入一些“运行时派生规则”（不落库）：
    - requires_batch / requires_dates / default_batch_code

    Phase M 第一阶段：
    - 真相源：expiry_policy
    - has_shelf_life 仅为镜像字段（legacy 名称），禁止在执行层/派生规则中读取作为依据
    """
    requires_batch = _is_required_expiry_policy(getattr(obj, "expiry_policy", None))
    setattr(obj, "requires_batch", True if requires_batch else False)
    setattr(obj, "requires_dates", True if requires_batch else False)
    # ✅ NONE：历史兼容默认 NOEXP（仅用于展示/旧调用），不作为写入语义
    setattr(obj, "default_batch_code", None if requires_batch else NOEXP_BATCH_CODE)
    return obj
