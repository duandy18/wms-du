# app/oms/deps/stores_order_sim_testset_guard.py
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text

from app.core.problem import make_problem


def extract_expanded_item_ids(out_dict: dict) -> list[int]:
    ids: set[int] = set()
    resolved = out_dict.get("resolved")
    if not isinstance(resolved, list):
        return []
    for r in resolved:
        if not isinstance(r, dict):
            continue
        exp = r.get("expanded_items")
        if not isinstance(exp, list):
            continue
        for it in exp:
            if not isinstance(it, dict):
                continue
            v = it.get("item_id")
            try:
                if v is None:
                    continue
                ids.add(int(v))
            except Exception:
                continue
    return sorted(ids)


async def _load_test_set_id(session, *, set_code: str) -> int:
    code = (set_code or "").strip()
    if not code:
        raise HTTPException(
            status_code=500,
            detail=make_problem(
                status_code=500,
                error_code="internal_error",
                message="测试集合不可用：set_code 不能为空",
                context={"set_code": set_code},
            ),
        )

    row = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM item_test_sets
                 WHERE code = :code
                 LIMIT 1
                """
            ),
            {"code": code},
        )
    ).mappings().first()

    if not row or row.get("id") is None:
        raise HTTPException(
            status_code=500,
            detail=make_problem(
                status_code=500,
                error_code="internal_error",
                message=f"测试集合不可用：测试集合不存在：{code}",
                context={"set_code": code},
            ),
        )

    return int(row["id"])


async def _load_test_set_member_item_ids(
    session,
    *,
    set_id: int,
    item_ids: list[int],
) -> set[int]:
    ids = sorted({int(x) for x in item_ids if x is not None})
    if not ids:
        return set()

    rows = (
        await session.execute(
            text(
                """
                SELECT item_id
                  FROM item_test_set_items
                 WHERE set_id = :set_id
                   AND item_id = ANY(:item_ids)
                """
            ),
            {"set_id": int(set_id), "item_ids": ids},
        )
    ).mappings().all()

    return {int(row["item_id"]) for row in rows if row.get("item_id") is not None}


async def assert_order_sim_all_items_in_test_set(
    *,
    session,
    out_dict: dict,
    platform: str,
    store_code: str,
    store_id: int,
) -> None:
    """
    ✅ 测试域硬隔离护栏：order-sim 必须“全部是测试商品”（DEFAULT 集合）
    """

    resolved_item_ids = extract_expanded_item_ids(out_dict if isinstance(out_dict, dict) else {})
    if not resolved_item_ids:
        return

    set_code = "DEFAULT"
    set_id = await _load_test_set_id(session, set_code=set_code)
    member_item_ids = await _load_test_set_member_item_ids(
        session,
        set_id=set_id,
        item_ids=resolved_item_ids,
    )

    out_of_set_item_ids = sorted(set(resolved_item_ids) - member_item_ids)
    if not out_of_set_item_ids:
        return

    raise HTTPException(
        status_code=409,
        detail=make_problem(
            status_code=409,
            error_code="conflict",
            message=f"order-sim 仅允许测试商品：非测试商品 item_ids={out_of_set_item_ids}",
            context={
                "platform": platform,
                "store_code": store_code,
                "store_id": int(store_id),
                "set_code": set_code,
                "out_of_set_item_ids": out_of_set_item_ids,
                "resolved_item_ids": resolved_item_ids,
            },
        ),
    )
