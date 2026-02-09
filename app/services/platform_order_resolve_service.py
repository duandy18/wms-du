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
    # fsku_components.qty 是 numeric(18,6)，这里强制要求“整数形态”，避免 silent wrong。
    if q <= 0:
        return 0
    if q == q.to_integral_value():
        return int(q)
    raise ValueError(f"component qty must be integer-like, got={str(q)}")


# ---------------- Risk (resolve-side facts) ----------------
def _risk(level: str, flags: List[str], reason: str) -> Dict[str, Any]:
    # 统一输出形状（避免前端推断）：risk_flags/risk_level/risk_reason
    return {"risk_flags": list(flags), "risk_level": str(level), "risk_reason": str(reason)}


def _risk_high(flag: str, reason: str) -> Dict[str, Any]:
    return _risk("HIGH", [flag], reason)


def _risk_medium(flag: str, reason: str) -> Dict[str, Any]:
    return _risk("MEDIUM", [flag], reason)


@dataclass
class ResolvedLine:
    platform_sku_id: str
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


async def load_current_binding_fsku_id(
    session: AsyncSession,
    *,
    platform: str,
    store_id: int,
    platform_sku_id: str,
) -> int | None:
    plat = norm_platform(platform)
    pid = str(platform_sku_id).strip()

    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT fsku_id
                      FROM platform_sku_bindings
                     WHERE platform = :p
                       AND store_id = :sid
                       AND platform_sku_id = :psku
                       AND effective_to IS NULL
                     ORDER BY effective_from DESC
                     LIMIT 1
                    """
                ),
                {"p": plat, "sid": int(store_id), "psku": pid},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    fsku_id = row.get("fsku_id")
    return int(fsku_id) if fsku_id is not None else None


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
    输入：平台订单行（platform_sku_id + qty）
    输出：
      - resolved_lines：每行命中哪个 fsku、展开成哪些 item
      - unresolved：缺绑定/组件异常等原因（包含 risk_* 字段，供“可人工继续（标记风险）”使用）
      - item_qty_map：聚合后的 item_id -> need_qty（可直接喂给 OrderService.ingest）

    注意：
    - 本函数只做“读侧裁决 + 风险事实输出”，不做任何写侧 binding。
    """
    plat = norm_platform(platform)

    resolved_lines: List[ResolvedLine] = []
    unresolved: List[Dict[str, Any]] = []
    item_qty_map: Dict[int, int] = {}

    for ln in lines or []:
        psku = str(ln.get("platform_sku_id") or "").strip()
        qty = to_int_pos(ln.get("qty"), default=1)

        if not psku:
            # ⚠️ 行缺少 PSKU：无法建立治理锚点，也无法解析；允许人工继续但必须风险标记
            unresolved.append(
                {
                    "platform_sku_id": "",
                    "qty": qty,
                    "reason": "MISSING_PSKU",
                    "hint": "platform_sku_id 不能为空",
                    **_risk_high("PSKU_CODE_MISSING", "缺少 PSKU/规格编码：需人工补录或纳入治理后再继续。"),
                }
            )
            continue

        fsku_id = await load_current_binding_fsku_id(session, platform=plat, store_id=store_id, platform_sku_id=psku)
        if not fsku_id:
            # ⚠️ 没有 current binding：典型治理入口
            unresolved.append(
                {
                    "platform_sku_id": psku,
                    "qty": qty,
                    "reason": "MISSING_BINDING",
                    "hint": "请先为该 PSKU 建立当前生效绑定（PSKU->FSKU）。",
                    **_risk_high("PSKU_BINDING_MISSING", "该 PSKU 尚未建立 current 绑定：允许人工继续，但必须尽快治理。"),
                }
            )
            continue

        comps = await load_fsku_components(session, fsku_id=fsku_id)
        if not comps:
            # ⚠️ 绑定到了非 published / 或无 components：属于“绑定存在但不可执行”
            unresolved.append(
                {
                    "platform_sku_id": psku,
                    "qty": qty,
                    "fsku_id": fsku_id,
                    "reason": "FSKU_NO_COMPONENTS_OR_NOT_PUBLISHED",
                    "hint": "该 FSKU 未发布或未配置 components。",
                    **_risk_high("FSKU_NOT_EXECUTABLE", "绑定目标 FSKU 不可执行（未发布或无 components）：允许人工继续，但需修复绑定/发布。"),
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
                expanded.append({"item_id": item_id, "component_qty": cqty, "need_qty": need, "role": c.get("role")})
        except Exception as e:
            unresolved.append(
                {
                    "platform_sku_id": psku,
                    "qty": qty,
                    "fsku_id": fsku_id,
                    "reason": "COMPONENT_QTY_INVALID",
                    "hint": str(e),
                    **_risk_high("FSKU_COMPONENT_INVALID", "FSKU components 数量非法：需修复组件结构后再继续。"),
                }
            )
            continue

        resolved_lines.append(
            ResolvedLine(
                platform_sku_id=psku,
                qty=qty,
                fsku_id=fsku_id,
                expanded_items=expanded,
            )
        )

    return resolved_lines, unresolved, item_qty_map
