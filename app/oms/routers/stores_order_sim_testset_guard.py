# app/api/routers/stores_routes_order_sim_testset_guard.py
from __future__ import annotations

from fastapi import HTTPException

from app.api.problem import make_problem
from app.services.item_test_set_service import ItemTestSetService


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


async def assert_order_sim_all_items_in_test_set(*, session, out_dict: dict, platform: str, shop_id: str, store_id: int) -> None:
    """
    ✅ 测试域硬隔离护栏：order-sim 必须“全部是测试商品”（DEFAULT 集合）
    """
    try:
        item_ids = extract_expanded_item_ids(out_dict if isinstance(out_dict, dict) else {})
        ts = ItemTestSetService(session)
        await ts.assert_items_in_test_set(item_ids=item_ids, set_code="DEFAULT")
    except ItemTestSetService.NotFound as e:
        raise HTTPException(
            status_code=500,
            detail=make_problem(
                status_code=500,
                error_code="internal_error",
                message=f"测试集合不可用：{e.message}",
                context={"platform": platform, "shop_id": shop_id, "store_id": int(store_id), "set_code": "DEFAULT"},
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
                    "platform": platform,
                    "shop_id": shop_id,
                    "store_id": int(store_id),
                    "set_code": e.set_code,
                    "out_of_set_item_ids": e.out_of_set_item_ids,
                    "resolved_item_ids": extract_expanded_item_ids(out_dict if isinstance(out_dict, dict) else {}),
                },
            ),
        )
