# app/oms/services/platform_order_ingest_universe_guard.py
from __future__ import annotations

import os
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession


def _get_test_store_code() -> str | None:
    s = (os.getenv("TEST_STORE_ID") or "").strip()
    return s or None


def is_test_store(store_code: str) -> bool:
    tid = _get_test_store_code()
    if tid is None:
        return False
    return str(store_code) == tid


def extract_item_ids_from_items_payload(items_payload: Sequence[Mapping[str, Any]]) -> list[int]:
    """
    从 items_payload 提取 item_id 列表（兼容不同 payload 形态）。
    约定优先级：
      1) item_id
      2) id
    """
    ids: set[int] = set()
    for it in items_payload or ():
        if not isinstance(it, Mapping):
            continue
        v = it.get("item_id")
        if v is None:
            v = it.get("id")
        if v is None:
            continue
        try:
            ids.add(int(v))
        except Exception:
            continue
    return sorted(ids)


async def enforce_no_test_items_in_non_test_store(
    session: AsyncSession,
    *,
    store_code: str,
    store_id: Optional[int],
    item_ids: list[int],
    source: str,
) -> None:
    """
    商品集合隔离机制已退役。

    历史上这里用于商品级隔离。
    现在只保留 platform_test_stores 作为测试店铺识别，不再按商品集合阻断。
    """
    return None
