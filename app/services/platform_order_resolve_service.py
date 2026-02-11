# app/services/platform_order_resolve_service.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.platform_order_resolve_core import resolve_platform_lines_to_items as _resolve_platform_lines_to_items
from app.services.platform_order_resolve_loaders import load_items_brief as _load_items_brief
from app.services.platform_order_resolve_store import resolve_store_id as _resolve_store_id
from app.services.platform_order_resolve_utils import (
    ResolvedLine,
    dec_to_int_qty as dec_to_int_qty,
    norm_platform as norm_platform,
    norm_shop_id as norm_shop_id,
    to_dec as to_dec,
    to_int_pos as to_int_pos,
)

# ✅ Public re-exports (保持旧 import 不炸)
# - 旧代码可能 import: norm_platform / norm_shop_id / to_int_pos / to_dec / dec_to_int_qty
# - 解析主入口也仍旧从此文件 import
__all__ = [
    "ResolvedLine",
    "norm_platform",
    "norm_shop_id",
    "to_int_pos",
    "to_dec",
    "dec_to_int_qty",
    "resolve_store_id",
    "load_items_brief",
    "resolve_platform_lines_to_items",
]


async def resolve_store_id(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    store_name: Optional[str],
) -> int:
    return await _resolve_store_id(session, platform=platform, shop_id=shop_id, store_name=store_name)


async def load_items_brief(
    session: AsyncSession,
    *,
    item_ids: List[int],
) -> Dict[int, Dict[str, Any]]:
    return await _load_items_brief(session, item_ids=item_ids)


async def resolve_platform_lines_to_items(
    session: AsyncSession,
    *,
    platform: str,
    store_id: int,
    lines: List[Dict[str, Any]],
) -> Tuple[List[ResolvedLine], List[Dict[str, Any]], Dict[int, int]]:
    return await _resolve_platform_lines_to_items(session, platform=platform, store_id=store_id, lines=lines)
