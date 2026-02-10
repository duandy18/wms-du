# app/api/routers/platform_orders_fact_repo.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def line_key_from_inputs(*, filled_code: Optional[str], line_no: Optional[int]) -> Optional[str]:
    """
    与 app/services/platform_order_fact_service._line_key 对齐（保持幂等键物理格式不变）：

    - 有填写码（filled_code 非空）：PSKU:{filled_code}
    - 无填写码（filled_code 为空）：NO_PSKU:{line_no}

    注意：PSKU/NO_PSKU 是历史前缀字符串，仅用于构造幂等键格式；
    不承载“平台 SKU/PSKU”业务语义。重命名前缀字符串需另起带迁移/兼容的 phase。
    """
    fc = (filled_code or "").strip()
    if fc:
        return f"PSKU:{fc}"
    if line_no is None:
        return None
    return f"NO_PSKU:{int(line_no)}"


async def load_shop_id_by_store_id(session: AsyncSession, *, store_id: int) -> str:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT shop_id
                      FROM stores
                     WHERE id = :id
                     LIMIT 1
                    """
                ),
                {"id": int(store_id)},
            )
        )
        .mappings()
        .first()
    )
    shop = (row.get("shop_id") if row else None) if row is not None else None
    if not shop:
        raise LookupError(f"store not found: store_id={store_id}")
    return str(shop)


async def load_fact_lines_for_order(
    session: AsyncSession,
    *,
    platform: str,
    store_id: int,
    ext_order_no: str,
) -> List[Dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT
                    line_no,
                    line_key,
                    locator_kind,
                    locator_value,
                    filled_code,
                    qty,
                    title,
                    spec,
                    extras
                  FROM platform_order_lines
                 WHERE platform = :platform
                   AND store_id = :store_id
                   AND ext_order_no = :ext_order_no
                 ORDER BY line_no ASC
                """
            ),
            {"platform": str(platform), "store_id": int(store_id), "ext_order_no": str(ext_order_no)},
        )
    ).mappings().all()

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "line_no": int(r.get("line_no") or 0),
                "line_key": str(r.get("line_key") or ""),
                "locator_kind": (r.get("locator_kind") or None),
                "locator_value": (r.get("locator_value") or None),
                "filled_code": (r.get("filled_code") or None),
                "qty": int(r.get("qty") or 1),
                "title": r.get("title"),
                "spec": r.get("spec"),
                "extras": r.get("extras"),
            }
        )
    return out
