# app/services/platform_order_fact_service.py
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.platform_order_resolve_service import norm_platform, norm_shop_id


def _line_key(*, filled_code: str | None, line_no: int) -> str:
    """
    行级幂等键（物理格式沿用历史前缀，不承载“PSKU 语义”）：

    - 有填写码（filled_code 非空）：PSKU:{filled_code}
    - 无填写码（filled_code 为空）：NO_PSKU:{line_no}

    注意：
    1) 这里的 PSKU/NO_PSKU 只是“历史前缀字符串”，属于幂等键格式的一部分。
       在当前系统语义中，填写码的唯一事实字段是 filled_code，与“平台 SKU/PSKU”概念已无耦合。
    2) 若要把前缀字符串重命名为 FILLED/NO_FILLED 等，必须另起带迁移与兼容策略的 phase；
       直接改这里会改变 upsert 冲突键，从而破坏幂等并导致事实行重复写入。
    """
    fc = (filled_code or "").strip()
    if fc:
        return f"PSKU:{fc}"
    return f"NO_PSKU:{int(line_no)}"


def _locator(*, filled_code: str | None, line_no: int) -> Tuple[str, str]:
    """
    对外/对人定位语义（与幂等键 line_key 分层）：

    - 有填写码：('FILLED_CODE', filled_code)
    - 无填写码：('LINE_NO', str(line_no))

    注意：这是语义定位，不参与幂等冲突键。
    """
    fc = (filled_code or "").strip()
    if fc:
        return "FILLED_CODE", fc
    return "LINE_NO", str(int(line_no))


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
        filled_code = (ln.get("filled_code") or "").strip() or None
        qty = int(ln.get("qty") or 0) if int(ln.get("qty") or 0) > 0 else 1
        title = ln.get("title")
        spec = ln.get("spec")
        extras = ln.get("extras")

        line_no = int(ln.get("line_no") or idx)
        lk = _line_key(filled_code=filled_code, line_no=line_no)
        locator_kind, locator_value = _locator(filled_code=filled_code, line_no=line_no)

        await session.execute(
            text(
                """
                INSERT INTO platform_order_lines(
                  platform, shop_id, store_id, ext_order_no,
                  line_no, line_key,
                  locator_kind, locator_value,
                  filled_code, qty, title, spec,
                  extras, raw_payload,
                  created_at, updated_at
                )
                VALUES(
                  :platform, :shop_id, :store_id, :ext_order_no,
                  :line_no, :line_key,
                  :locator_kind, :locator_value,
                  :filled_code, :qty, :title, :spec,
                  (:extras)::jsonb, (:raw_payload)::jsonb,
                  now(), now()
                )
                ON CONFLICT (platform, shop_id, ext_order_no, line_key)
                DO UPDATE SET
                  store_id       = EXCLUDED.store_id,
                  locator_kind   = EXCLUDED.locator_kind,
                  locator_value  = EXCLUDED.locator_value,
                  filled_code    = EXCLUDED.filled_code,
                  qty            = EXCLUDED.qty,
                  title          = EXCLUDED.title,
                  spec           = EXCLUDED.spec,
                  extras         = EXCLUDED.extras,
                  raw_payload    = EXCLUDED.raw_payload,
                  updated_at     = now()
                """
            ),
            {
                "platform": plat,
                "shop_id": sid,
                "store_id": int(store_id) if store_id is not None else None,
                "ext_order_no": ext,
                "line_no": line_no,
                "line_key": lk,
                "locator_kind": locator_kind,
                "locator_value": locator_value,
                "filled_code": filled_code,
                "qty": qty,
                "title": None if title is None else str(title),
                "spec": None if spec is None else str(spec),
                "extras": json.dumps(extras or {}, ensure_ascii=False),
                "raw_payload": json.dumps(raw_payload or {}, ensure_ascii=False),
            },
        )

    return len(lines or [])
