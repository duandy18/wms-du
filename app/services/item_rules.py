# app/services/item_rules.py
from __future__ import annotations

from app.models.item import Item

NOEXP_BATCH_CODE = "NOEXP"


def decorate_rules(obj: Item) -> Item:
    """
    给 Item 注入一些“运行时派生规则”（不落库）：
    - requires_batch / requires_dates / default_batch_code
    """
    has_sl = bool(getattr(obj, "has_shelf_life", False))
    setattr(obj, "requires_batch", True if has_sl else False)
    setattr(obj, "requires_dates", True if has_sl else False)
    setattr(obj, "default_batch_code", None if has_sl else NOEXP_BATCH_CODE)
    return obj
