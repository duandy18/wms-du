# app/services/platform_order_ingest_universe_guard.py
from __future__ import annotations

import os
from typing import Any, Mapping, Optional, Sequence

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import make_problem
from app.services.item_test_set_service import ItemTestSetService


def _get_test_shop_id() -> str | None:
    s = (os.getenv("TEST_SHOP_ID") or "").strip()
    return s or None


def is_test_shop(shop_id: str) -> bool:
    tid = _get_test_shop_id()
    if tid is None:
        return False
    return str(shop_id) == tid


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


async def enforce_no_test_items_in_non_test_shop(
    session: AsyncSession,
    *,
    shop_id: str,
    store_id: Optional[int],
    item_ids: list[int],
    source: str,
) -> None:
    """
    宇宙边界兜底（不污染 resolver）：

    当 TEST_SHOP_ID 设置后：
      - 非 TEST shop：禁止出现 DEFAULT Test Set items
      - TEST shop：不在这里强制“必须全是测试商品”（那条更偏 dev/order-sim 入口约束）
    """
    tid = _get_test_shop_id()
    if tid is None:
        return

    if is_test_shop(shop_id):
        return

    if not item_ids:
        return

    ts = ItemTestSetService(session)
    try:
        await ts.assert_items_not_in_test_set(item_ids=item_ids, set_code="DEFAULT")
    except ItemTestSetService.NotFound as e:
        raise HTTPException(
            status_code=500,
            detail=make_problem(
                status_code=500,
                error_code="internal_error",
                message=f"测试集合不可用：{e.message}",
                context={"shop_id": str(shop_id), "test_shop_id": str(tid), "set_code": "DEFAULT", "source": source},
            ),
        )
    except ItemTestSetService.Conflict as e:
        raise HTTPException(
            status_code=409,
            detail=make_problem(
                status_code=409,
                error_code="conflict",
                message=e.message,
                context={
                    "shop_id": str(shop_id),
                    "test_shop_id": str(tid),
                    "store_id": int(store_id) if store_id is not None else None,
                    "set_code": e.set_code,
                    "out_of_set_item_ids": e.out_of_set_item_ids,
                    "source": source,
                },
            ),
        )
