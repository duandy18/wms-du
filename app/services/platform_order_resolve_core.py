# app/services/platform_order_resolve_core.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.platform_order_resolve_binding import resolve_fsku_id_by_binding
from app.services.platform_order_resolve_loaders import load_fsku_components
from app.services.platform_order_resolve_store import load_shop_id_by_store_id
from app.services.platform_order_resolve_utils import (
    ResolvedLine,
    dec_to_int_qty,
    norm_platform,
    risk_high,
    to_dec,
    to_int_pos,
)


def _governance_jump_action(*, platform: str, store_id: int, merchant_code: str) -> Dict[str, Any]:
    # ✅ 不绑定前端 URL；只提供可执行动作与定位参数（前端自行路由）
    return {
        "action": "go_store_fsku_binding_governance",
        "label": "前往绑定治理（定位到该店铺商品代码）",
        "payload": {
            "platform": platform,
            "store_id": int(store_id),
            "merchant_code": merchant_code,
        },
    }


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
      1) filled_code → merchant_code_fsku_bindings（一对一）→ published FSKU.id
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
    shop_id = await load_shop_id_by_store_id(session, platform=plat, store_id=sid)

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
                    **risk_high(
                        "FILLED_CODE_MISSING",
                        "缺少填写码：无法解析商品；需人工补录或确认",
                    ),
                }
            )
            continue

        fsku_id: Optional[int] = None

        # 1) 优先走 binding（一对一）
        if shop_id:
            bid_fsku_id, bid_reason = await resolve_fsku_id_by_binding(
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
                            },
                            # ✅ 闭环：一键跳治理页定位到 merchant_code 行
                            _governance_jump_action(platform=plat, store_id=sid, merchant_code=filled_code),
                        ],
                        **risk_high(
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
                        # ✅ 既有契约：第一条必须是 bind_merchant_code（endpoint + payload）
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
                        },
                        # ✅ 新增闭环：治理页跳转 + 自动定位
                        _governance_jump_action(platform=plat, store_id=sid, merchant_code=filled_code),
                    ],
                    **risk_high(
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
                    **risk_high(
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
                    **risk_high(
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
