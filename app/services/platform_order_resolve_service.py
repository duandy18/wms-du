# app/services/platform_order_resolve_service.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.store_service import StoreService


def norm_platform(v: str) -> str:
    return (v or "").strip().upper()


def norm_shop_id(v: str) -> str:
    return str(v or "").strip()


def to_int_pos(v: Any, *, default: int = 1) -> int:
    try:
        n = int(v)
        return n if n > 0 else default
    except Exception:
        return default


def to_dec(v: Any) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def dec_to_int_qty(q: Decimal) -> int:
    if q <= 0:
        return 0
    if q == q.to_integral_value():
        return int(q)
    raise ValueError(f"component qty must be integer-like, got={str(q)}")


# ---------------- Risk helpers ----------------
def _risk(level: str, flags: List[str], reason: str) -> Dict[str, Any]:
    return {
        "risk_flags": list(flags),
        "risk_level": str(level),
        "risk_reason": str(reason),
    }


def _risk_high(flag: str, reason: str) -> Dict[str, Any]:
    return _risk("HIGH", [flag], reason)


def _risk_medium(flag: str, reason: str) -> Dict[str, Any]:
    return _risk("MEDIUM", [flag], reason)


@dataclass
class ResolvedLine:
    filled_code: str
    qty: int
    fsku_id: int
    expanded_items: List[Dict[str, Any]]


async def resolve_store_id(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    store_name: Optional[str],
) -> int:
    plat = norm_platform(platform)
    sid = norm_shop_id(shop_id)

    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT id
                      FROM stores
                     WHERE platform = :p
                       AND shop_id  = :s
                     LIMIT 1
                    """
                ),
                {"p": plat, "s": sid},
            )
        )
        .mappings()
        .first()
    )
    if row and row.get("id") is not None:
        return int(row["id"])

    await StoreService.ensure_store(
        session,
        platform=plat,
        shop_id=sid,
        name=store_name or f"{plat}-{sid}",
    )

    row2 = (
        (
            await session.execute(
                text(
                    """
                    SELECT id
                      FROM stores
                     WHERE platform = :p
                       AND shop_id  = :s
                     LIMIT 1
                    """
                ),
                {"p": plat, "s": sid},
            )
        )
        .mappings()
        .first()
    )
    if not row2 or row2.get("id") is None:
        raise RuntimeError(f"ensure_store failed: platform={plat} shop_id={sid}")
    return int(row2["id"])


async def load_fsku_components(
    session: AsyncSession,
    *,
    fsku_id: int,
) -> List[Dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT c.item_id, c.qty, c.role
                  FROM fsku_components c
                  JOIN fskus f ON f.id = c.fsku_id
                 WHERE c.fsku_id = :fid
                   AND f.status = 'published'
                 ORDER BY c.id
                """
            ),
            {"fid": int(fsku_id)},
        )
    ).mappings().all()

    return [dict(r) for r in rows]


async def load_items_brief(
    session: AsyncSession,
    *,
    item_ids: List[int],
) -> Dict[int, Dict[str, Any]]:
    if not item_ids:
        return {}
    rows = (
        await session.execute(
            text(
                """
                SELECT id, sku, name
                  FROM items
                 WHERE id = ANY(:ids)
                """
            ),
            {"ids": [int(x) for x in item_ids]},
        )
    ).mappings().all()

    out: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        out[int(r["id"])] = {"sku": r.get("sku"), "name": r.get("name")}
    return out


async def resolve_platform_lines_to_items(
    session: AsyncSession,
    *,
    platform: str,
    store_id: int,
    lines: List[Dict[str, Any]],
) -> Tuple[List[ResolvedLine], List[Dict[str, Any]], Dict[int, int]]:
    """
    Phase N+2 · 解析核心

    输入：
      - 行级字段：filled_code + qty

    解析路径：
      filled_code → FSKU.code → published FSKU → fsku_components → items

    说明：
    - 不存在 PSKU / mirror / binding
    - 事实表唯一事实字段为 filled_code（字段语义已完成收敛）
    """


    resolved_lines: List[ResolvedLine] = []
    unresolved: List[Dict[str, Any]] = []
    item_qty_map: Dict[int, int] = {}

    for ln in lines or []:
        filled_code = str(ln.get("filled_code") or "").strip()
        qty = to_int_pos(ln.get("qty"), default=1)

        if not filled_code:
            unresolved.append(
                {
                    "filled_code": "",
                    "qty": qty,
                    "reason": "MISSING_FILLED_CODE",
                    "hint": "未提供填写码",
                    **_risk_high(
                        "FILLED_CODE_MISSING",
                        "缺少填写码：无法解析商品；需人工补录或确认",
                    ),
                }
            )
            continue

        row = (
            (
                await session.execute(
                    text(
                        """
                        SELECT id
                          FROM fskus
                         WHERE code = :code
                           AND status = 'published'
                         LIMIT 1
                        """
                    ),
                    {"code": filled_code},
                )
            )
            .mappings()
            .first()
        )

        if not row or row.get("id") is None:
            unresolved.append(
                {
                    "filled_code": filled_code,
                    "qty": qty,
                    "reason": "FSKU_NOT_FOUND",
                    "hint": "未找到已发布的 FSKU",
                    **_risk_high(
                        "FSKU_NOT_FOUND",
                        "填写码未命中任何已发布 FSKU；需人工确认",
                    ),
                }
            )
            continue

        fsku_id = int(row["id"])

        comps = await load_fsku_components(session, fsku_id=fsku_id)
        if not comps:
            unresolved.append(
                {
                    "filled_code": filled_code,
                    "qty": qty,
                    "fsku_id": fsku_id,
                    "reason": "FSKU_NOT_EXECUTABLE",
                    "hint": "FSKU 未配置组件或未发布",
                    **_risk_high(
                        "FSKU_NOT_EXECUTABLE",
                        "填写码命中的 FSKU 不可执行；需修复组件配置",
                    ),
                }
            )
            continue

        expanded: List[Dict[str, Any]] = []
        try:
            for c in comps:
                item_id = int(c["item_id"])
                cqty = dec_to_int_qty(to_dec(c["qty"]))
                need = int(qty) * int(cqty)
                if need <= 0:
                    continue
                item_qty_map[item_id] = int(item_qty_map.get(item_id, 0)) + need
                expanded.append(
                    {
                        "item_id": item_id,
                        "component_qty": cqty,
                        "need_qty": need,
                        "role": c.get("role"),
                    }
                )
        except Exception as e:
            unresolved.append(
                {
                    "filled_code": filled_code,
                    "qty": qty,
                    "fsku_id": fsku_id,
                    "reason": "COMPONENT_QTY_INVALID",
                    "hint": str(e),
                    **_risk_high(
                        "FSKU_COMPONENT_INVALID",
                        "FSKU 组件数量非法；需修复后再继续",
                    ),
                }
            )
            continue

        resolved_lines.append(
            ResolvedLine(
                filled_code=filled_code,
                qty=qty,
                fsku_id=fsku_id,
                expanded_items=expanded,
            )
        )

    return resolved_lines, unresolved, item_qty_map
