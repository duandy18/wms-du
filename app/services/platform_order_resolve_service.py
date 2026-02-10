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


async def _load_shop_id_by_store_id(
    session: AsyncSession,
    *,
    platform: str,
    store_id: int,
) -> Optional[str]:
    """
    用 store_id 反查平台 shop_id（绑定表唯一域是 platform+shop_id+merchant_code）。
    """
    plat = norm_platform(platform)
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT shop_id
                      FROM stores
                     WHERE id = :sid
                       AND platform = :p
                     LIMIT 1
                    """
                ),
                {"sid": int(store_id), "p": plat},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    v = row.get("shop_id")
    return norm_shop_id(str(v)) if v is not None else None


async def _resolve_fsku_id_by_binding_current(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    merchant_code: str,
) -> Tuple[Optional[int], Optional[str]]:
    """
    返回 (fsku_id, reason_if_not_ok)

    reason:
      - None: 命中 published FSKU
      - FSKU_NOT_PUBLISHED: 绑定存在但指向非 published
      - CODE_NOT_BOUND: 未找到 current 绑定
    """
    plat = norm_platform(platform)
    sid = norm_shop_id(shop_id)
    code = (merchant_code or "").strip()
    if not code:
        return (None, "CODE_NOT_BOUND")

    # 1) 优先：current + published
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT b.fsku_id
                      FROM merchant_code_fsku_bindings b
                      JOIN fskus f ON f.id = b.fsku_id
                     WHERE b.platform = :p
                       AND b.shop_id = :shop_id
                       AND b.merchant_code = :code
                       AND b.effective_to IS NULL
                       AND f.status = 'published'
                     LIMIT 1
                    """
                ),
                {"p": plat, "shop_id": sid, "code": code},
            )
        )
        .mappings()
        .first()
    )
    if row and row.get("fsku_id") is not None:
        return (int(row["fsku_id"]), None)

    # 2) 再查：current 存在但非 published（给更精确原因）
    row2 = (
        (
            await session.execute(
                text(
                    """
                    SELECT b.fsku_id, f.status
                      FROM merchant_code_fsku_bindings b
                      LEFT JOIN fskus f ON f.id = b.fsku_id
                     WHERE b.platform = :p
                       AND b.shop_id = :shop_id
                       AND b.merchant_code = :code
                       AND b.effective_to IS NULL
                     LIMIT 1
                    """
                ),
                {"p": plat, "shop_id": sid, "code": code},
            )
        )
        .mappings()
        .first()
    )
    if row2 and row2.get("fsku_id") is not None:
        st = str(row2.get("status") or "")
        if st and st != "published":
            return (None, "FSKU_NOT_PUBLISHED")
        return (None, "CODE_NOT_BOUND")

    return (None, "CODE_NOT_BOUND")


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
    Phase N+3 · 解析核心（引入“人工绑定复用”但不引入字符串猜测）

    输入：
      - 行级字段：filled_code + qty

    解析路径（严格确定性）：
      1) filled_code → merchant_code_fsku_bindings(current) → published FSKU.id
      2) 若 1) 未命中：回退 filled_code == FSKU.code（理想路径）
      3) 命中 FSKU.id 后：published FSKU → fsku_components → items

    说明：
    - 事实表唯一事实字段仍为 filled_code（字段语义已收敛）
    - “绑定表”仅用于复用人工确认结果（允许 filled_code != FSKU.code）
    - 不做 title/spec 自动匹配、不做模糊猜测
    """

    resolved_lines: List[ResolvedLine] = []
    unresolved: List[Dict[str, Any]] = []
    item_qty_map: Dict[int, int] = {}

    plat = norm_platform(platform)
    sid = int(store_id)
    shop_id = await _load_shop_id_by_store_id(session, platform=plat, store_id=sid)

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
                    "next_actions": [
                        {
                            "action": "fill_filled_code",
                            "label": "补填填写码（商家规格编码 / filled_code）后再接入",
                        }
                    ],
                    **_risk_high(
                        "FILLED_CODE_MISSING",
                        "缺少填写码：无法解析商品；需人工补录或确认",
                    ),
                }
            )
            continue

        fsku_id: Optional[int] = None

        # 1) 优先走 binding current
        if shop_id:
            bid_fsku_id, bid_reason = await _resolve_fsku_id_by_binding_current(
                session,
                platform=plat,
                shop_id=shop_id,
                merchant_code=filled_code,
            )
            if bid_fsku_id is not None:
                fsku_id = int(bid_fsku_id)
            elif bid_reason == "FSKU_NOT_PUBLISHED":
                unresolved.append(
                    {
                        "filled_code": filled_code,
                        "qty": qty,
                        "reason": "FSKU_NOT_PUBLISHED",
                        "hint": "填写码已绑定，但目标 FSKU 非 published",
                        "next_actions": [
                            {
                                "action": "rebind_merchant_code",
                                "label": "重新绑定填写码到一个已发布 FSKU",
                                "payload": {
                                    "platform": plat,
                                    "store_id": sid,
                                    "filled_code": filled_code,
                                },
                            }
                        ],
                        **_risk_high(
                            "FSKU_NOT_PUBLISHED",
                            "填写码绑定到了未发布/已退休的 FSKU；需人工更正绑定或发布新 FSKU",
                        ),
                    }
                )
                continue

        # 2) 未命中 binding：回退到理想路径 filled_code == FSKU.code
        if fsku_id is None:
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
            if row and row.get("id") is not None:
                fsku_id = int(row["id"])

        # 3) 两条都没命中：明确告诉你“去绑定”
        if fsku_id is None:
            unresolved.append(
                {
                    "filled_code": filled_code,
                    "qty": qty,
                    "reason": "CODE_NOT_BOUND",
                    "hint": "填写码未绑定到可执行 FSKU",
                    "next_actions": [
                        {
                            "action": "bind_merchant_code",
                            "label": "人工绑定填写码到 FSKU（一次绑定，后续自动解析）",
                            "endpoint": "/platform-orders/manual-decisions/bind-merchant-code",
                            "payload": {
                                "platform": plat,
                                "store_id": sid,
                                "filled_code": filled_code,
                                "fsku_id": None,
                                "reason": "bind from resolver: CODE_NOT_BOUND",
                            },
                        }
                    ],
                    **_risk_high(
                        "CODE_NOT_BOUND",
                        "填写码未命中绑定表且不等于任何已发布 FSKU.code；需人工绑定后再继续",
                    ),
                }
            )
            continue

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
