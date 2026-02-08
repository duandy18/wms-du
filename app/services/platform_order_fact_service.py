# app/services/platform_order_fact_service.py
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.platform_order_resolve_service import norm_platform, norm_shop_id


def _line_key(*, platform_sku_id: str | None, line_no: int) -> str:
    """
    行级幂等键：
    - 有 PSKU：PSKU:{platform_sku_id}
    - 无 PSKU：NO_PSKU:{line_no}
    后续如果要支持文本匹配，可把 line_key 改成 hash(title/spec/...)
    """
    p = (platform_sku_id or "").strip()
    if p:
        return f"PSKU:{p}"
    return f"NO_PSKU:{int(line_no)}"


async def upsert_platform_order_lines(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    store_id: Optional[int],
    ext_order_no: str,
    lines: List[Dict[str, Any]],
    raw_payload: Optional[Dict[str, Any]] = None,
) -> int:
    """
    把平台订单行事实写入 platform_order_lines（幂等 by line_key）。
    返回：本次 upsert 的行数（按输入行数计）。
    """
    plat = norm_platform(platform)
    sid = norm_shop_id(shop_id)
    ext = str(ext_order_no or "").strip()
    if not ext:
        raise ValueError("ext_order_no is required")

    for idx, ln in enumerate(lines or [], start=1):
        psku = (ln.get("platform_sku_id") or "").strip() or None
        qty = int(ln.get("qty") or 0) if int(ln.get("qty") or 0) > 0 else 1
        title = ln.get("title")
        spec = ln.get("spec")
        extras = ln.get("extras")

        line_no = int(ln.get("line_no") or idx)
        lk = _line_key(platform_sku_id=psku, line_no=line_no)

        await session.execute(
            text(
                """
                INSERT INTO platform_order_lines(
                  platform, shop_id, store_id, ext_order_no,
                  line_no, line_key,
                  platform_sku_id, qty, title, spec,
                  extras, raw_payload,
                  created_at, updated_at
                )
                VALUES(
                  :platform, :shop_id, :store_id, :ext_order_no,
                  :line_no, :line_key,
                  :platform_sku_id, :qty, :title, :spec,
                  (:extras)::jsonb, (:raw_payload)::jsonb,
                  now(), now()
                )
                ON CONFLICT (platform, shop_id, ext_order_no, line_key)
                DO UPDATE SET
                  store_id        = EXCLUDED.store_id,
                  platform_sku_id = EXCLUDED.platform_sku_id,
                  qty             = EXCLUDED.qty,
                  title           = EXCLUDED.title,
                  spec            = EXCLUDED.spec,
                  extras          = EXCLUDED.extras,
                  raw_payload     = EXCLUDED.raw_payload,
                  updated_at      = now()
                """
            ),
            {
                "platform": plat,
                "shop_id": sid,
                "store_id": int(store_id) if store_id is not None else None,
                "ext_order_no": ext,
                "line_no": line_no,
                "line_key": lk,
                "platform_sku_id": psku,
                "qty": qty,
                "title": None if title is None else str(title),
                "spec": None if spec is None else str(spec),
                "extras": json.dumps(extras or {}, ensure_ascii=False),
                "raw_payload": json.dumps(raw_payload or {}, ensure_ascii=False),
            },
        )

    return len(lines or [])
