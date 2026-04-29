# app/oms/deps/stores_order_sim_testset_guard.py
from __future__ import annotations


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


async def assert_order_sim_all_items_in_test_set(
    *,
    session,
    out_dict: dict,
    platform: str,
    store_code: str,
    store_id: int,
) -> None:
    """
    商品集合隔离机制已退役。

    该函数保留为兼容入口，避免 order-sim 调用方立即大面积改名；
    现在不再按商品集合做强制校验。
    """
    return None
