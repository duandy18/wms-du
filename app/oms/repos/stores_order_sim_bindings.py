# app/api/routers/stores_order_sim_bindings_repo.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _fmt_qty(v: Any) -> str:
    """
    fsku_components.qty 是 Numeric -> Decimal。
    展示：去掉多余 0，避免科学计数法，保持稳定可读。
    """
    if v is None:
        return "0"
    if isinstance(v, Decimal):
        d = v
    else:
        try:
            d = Decimal(str(v))
        except Exception:
            return str(v)

    if d == 0:
        return "0"

    n = d.normalize()
    s = format(n, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


async def list_bound_filled_code_options(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
) -> List[Dict[str, Any]]:
    """
    只用 A：已绑定 merchant_code → published FSKU。
    返回：filled_code + suggested_title + components_summary（spec 只读展示）。

    组件摘要：优先 items.name（人类可读），缺 name 时回退 items.sku。
    输出格式：每个组件一行（用 \\n 分隔）。
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT
                  b.merchant_code AS filled_code,
                  b.fsku_id       AS fsku_id,
                  f.name          AS fsku_name
                FROM merchant_code_fsku_bindings b
                JOIN fskus f
                  ON f.id = b.fsku_id
                 AND f.status = 'published'
               WHERE b.platform = :p
                 AND b.shop_id   = :s
               ORDER BY b.merchant_code ASC
                """
            ),
            {"p": str(platform), "s": str(shop_id)},
        )
    ).mappings().all()

    if not rows:
        return []

    fsku_ids = [int(r["fsku_id"]) for r in rows if r.get("fsku_id") is not None]
    if not fsku_ids:
        return []

    comp_rows = (
        await session.execute(
            text(
                """
                SELECT
                  c.fsku_id  AS fsku_id,
                  COALESCE(i.name, i.sku) AS item_name,
                  c.qty      AS qty,
                  c.role     AS role
                FROM fsku_components c
                JOIN items i
                  ON i.id = c.item_id
               WHERE c.fsku_id = ANY(:ids)
               ORDER BY c.fsku_id ASC,
                        CASE WHEN c.role = 'primary' THEN 0 ELSE 1 END,
                        COALESCE(i.name, i.sku) ASC
                """
            ),
            {"ids": fsku_ids},
        )
    ).mappings().all()

    comps_by_fsku: Dict[int, List[Dict[str, Any]]] = {}
    for cr in comp_rows:
        fid = int(cr["fsku_id"])
        comps_by_fsku.setdefault(fid, []).append(
            {
                "name": str(cr.get("item_name") or ""),
                "qty": cr.get("qty"),
                "role": str(cr.get("role") or ""),
            }
        )

    def _summary(fid: int) -> str:
        parts: List[str] = []
        for it in comps_by_fsku.get(fid, []):
            name = str(it.get("name") or "")
            qty_s = _fmt_qty(it.get("qty"))
            role = str(it.get("role") or "")
            if not name or qty_s == "0":
                continue
            if role:
                parts.append(f"{name}*{qty_s}({role})")
            else:
                parts.append(f"{name}*{qty_s}")
        return "\n".join(parts)

    out: List[Dict[str, Any]] = []
    for r in rows:
        fid = int(r["fsku_id"])
        out.append(
            {
                "filled_code": str(r["filled_code"]),
                "suggested_title": str(r.get("fsku_name") or ""),
                "components_summary": _summary(fid),
            }
        )
    return out


async def build_components_summary_by_filled_code(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    filled_code: str,
) -> Optional[str]:
    """
    spec 的唯一来源：merchant_code(current) -> published fsku -> components -> items
    未绑定或非 published => None

    组件摘要：优先 items.name（人类可读），缺 name 时回退 items.sku。
    输出格式：每个组件一行（用 \\n 分隔）。
    """
    cd = (filled_code or "").strip()
    if not cd:
        return None

    row = (
        await session.execute(
            text(
                """
                SELECT f.id AS fsku_id
                  FROM merchant_code_fsku_bindings b
                  JOIN fskus f
                    ON f.id = b.fsku_id
                   AND f.status = 'published'
                 WHERE b.platform = :p
                   AND b.shop_id   = :s
                   AND b.merchant_code = :c
                 LIMIT 1
                """
            ),
            {"p": str(platform), "s": str(shop_id), "c": cd},
        )
    ).mappings().first()

    if not row or row.get("fsku_id") is None:
        return None

    fid = int(row["fsku_id"])
    comp_rows = (
        await session.execute(
            text(
                """
                SELECT
                  COALESCE(i.name, i.sku) AS item_name,
                  c.qty  AS qty,
                  c.role AS role
                FROM fsku_components c
                JOIN items i ON i.id = c.item_id
               WHERE c.fsku_id = :fid
               ORDER BY CASE WHEN c.role = 'primary' THEN 0 ELSE 1 END,
                        COALESCE(i.name, i.sku) ASC
                """
            ),
            {"fid": fid},
        )
    ).mappings().all()

    parts: List[str] = []
    for cr in comp_rows:
        name = str(cr.get("item_name") or "")
        qty_s = _fmt_qty(cr.get("qty"))
        role = str(cr.get("role") or "")
        if not name or qty_s == "0":
            continue
        if role:
            parts.append(f"{name}*{qty_s}({role})")
        else:
            parts.append(f"{name}*{qty_s}")

    return "\n".join(parts)
