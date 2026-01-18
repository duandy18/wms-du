# app/services/order_ingest_routing.py
from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_writer import AuditEventWriter
from app.services.channel_inventory_service import ChannelInventoryService


def _normalize_province_from_address(address: Optional[Mapping[str, str]]) -> Optional[str]:
    """
    路线 C：province 来自订单收件省。

    合同（稳定版）：
    - 省份只要非空就接受（不再强制中文后缀）
    - 合法性由“是否能命中服务仓规则”决定：
        * 命中：继续校验整单履约
        * 不命中：NO_SERVICE_WAREHOUSE（显式阻断）
    - 测试辅助：若省份缺失，可通过环境变量 WMS_TEST_DEFAULT_PROVINCE 提供默认值（仅测试用）
    """
    raw = None
    if address:
        raw = str(address.get("province") or "").strip()
        if raw:
            return raw

    # 测试用兜底：只在显式设置时生效（避免污染生产）
    fallback = (os.getenv("WMS_TEST_DEFAULT_PROVINCE") or "").strip()
    return fallback or None


async def _resolve_service_warehouse_by_province(
    session: AsyncSession,
    *,
    province: str,
) -> Optional[int]:
    """
    按省命中唯一服务仓：
    - 依赖 warehouse_service_provinces.province_code 全局唯一（互斥）
    """
    row = await session.execute(
        text(
            """
            SELECT warehouse_id
              FROM warehouse_service_provinces
             WHERE province_code = :p
             LIMIT 1
            """
        ),
        {"p": province},
    )
    rec = row.first()
    if rec is None or rec[0] is None:
        return None
    return int(rec[0])


async def auto_route_warehouse_if_possible(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    order_id: int,
    order_ref: str,
    trace_id: Optional[str],
    items: Sequence[Mapping[str, Any]],
    address: Optional[Mapping[str, str]] = None,
) -> Optional[dict]:
    """
    路线 C（执行期约束满足式履约）：

    - 系统不“选仓”，只做约束校验
    - 唯一服务仓：按省命中 warehouse_service_provinces（互斥）
    - 校验服务仓能否整单履约（SKU 完整性 + 数量；当前先用可售数量校验）
    - 满足：标记 READY_TO_FULFILL，并写入 orders.warehouse_id / service_warehouse_id / fulfillment_warehouse_id
    - 不满足：标记 FULFILLMENT_BLOCKED + blocked_reasons/detail；不写 orders.warehouse_id（让下游 reserve 正确停下）

    返回：
      None：未处理（items 为空 / qty 全无效）
      dict：结果摘要（status, service_warehouse_id, province, reason, considered）
    """
    if not items:
        return None

    # 汇总每个 item 的总需求量
    target_qty: Dict[int, int] = {}
    for it in items:
        item_id = it.get("item_id")
        qty = int(it.get("qty") or 0)
        if item_id is None or qty <= 0:
            continue
        iid = int(item_id)
        target_qty[iid] = target_qty.get(iid, 0) + qty

    if not target_qty:
        return None

    plat_norm = platform.upper()

    province = _normalize_province_from_address(address)
    if not province:
        await session.execute(
            text(
                """
                UPDATE orders
                   SET fulfillment_status = 'FULFILLMENT_BLOCKED',
                       blocked_reasons    = CAST(:reasons AS jsonb),
                       blocked_detail     = :detail,
                       service_warehouse_id = NULL,
                       fulfillment_warehouse_id = NULL
                 WHERE id = :oid
                """
            ),
            {
                "oid": int(order_id),
                "reasons": '["NO_SERVICE_WAREHOUSE"]',
                "detail": "无法命中服务仓：订单收件省缺失",
            },
        )
        try:
            await AuditEventWriter.write(
                session,
                flow="OUTBOUND",
                event="FULFILLMENT_BLOCKED",
                ref=order_ref,
                trace_id=trace_id,
                meta={
                    "platform": plat_norm,
                    "shop": shop_id,
                    "province": None,
                    "service_warehouse_id": None,
                    "reason": "NO_SERVICE_WAREHOUSE",
                },
                auto_commit=False,
            )
        except Exception:
            pass
        return {
            "status": "FULFILLMENT_BLOCKED",
            "service_warehouse_id": None,
            "province": None,
            "reason": "NO_SERVICE_WAREHOUSE",
            "considered": [],
        }

    service_wid = await _resolve_service_warehouse_by_province(session, province=province)
    if service_wid is None:
        await session.execute(
            text(
                """
                UPDATE orders
                   SET fulfillment_status = 'FULFILLMENT_BLOCKED',
                       blocked_reasons    = CAST(:reasons AS jsonb),
                       blocked_detail     = :detail,
                       service_warehouse_id = NULL,
                       fulfillment_warehouse_id = NULL
                 WHERE id = :oid
                """
            ),
            {
                "oid": int(order_id),
                "reasons": '["NO_SERVICE_WAREHOUSE"]',
                "detail": f"无法命中服务仓：省份 {province} 未配置服务仓",
            },
        )
        try:
            await AuditEventWriter.write(
                session,
                flow="OUTBOUND",
                event="FULFILLMENT_BLOCKED",
                ref=order_ref,
                trace_id=trace_id,
                meta={
                    "platform": plat_norm,
                    "shop": shop_id,
                    "province": province,
                    "service_warehouse_id": None,
                    "reason": "NO_SERVICE_WAREHOUSE",
                },
                auto_commit=False,
            )
        except Exception:
            pass
        return {
            "status": "FULFILLMENT_BLOCKED",
            "service_warehouse_id": None,
            "province": province,
            "reason": "NO_SERVICE_WAREHOUSE",
            "considered": [],
        }

    # 校验：该服务仓能否整单履约（数量不足则 BLOCKED）
    channel_svc = ChannelInventoryService()
    insufficient: List[dict] = []
    for item_id, qty in target_qty.items():
        available_raw = await channel_svc.get_available_for_item(
            session=session,
            platform=plat_norm,
            shop_id=shop_id,
            warehouse_id=int(service_wid),
            item_id=int(item_id),
        )
        if qty > available_raw:
            insufficient.append(
                {
                    "item_id": int(item_id),
                    "need": int(qty),
                    "available": int(available_raw),
                }
            )

    if insufficient:
        await session.execute(
            text(
                """
                UPDATE orders
                   SET fulfillment_status = 'FULFILLMENT_BLOCKED',
                       blocked_reasons    = CAST(:reasons AS jsonb),
                       blocked_detail     = :detail,
                       service_warehouse_id = :swid,
                       fulfillment_warehouse_id = NULL
                 WHERE id = :oid
                """
            ),
            {
                "oid": int(order_id),
                "swid": int(service_wid),
                "reasons": '["INSUFFICIENT_QTY"]',
                "detail": f"服务仓库存不足：仓库 {service_wid} 无法整单履约（省份 {province}）",
            },
        )
        try:
            await AuditEventWriter.write(
                session,
                flow="OUTBOUND",
                event="FULFILLMENT_BLOCKED",
                ref=order_ref,
                trace_id=trace_id,
                meta={
                    "platform": plat_norm,
                    "shop": shop_id,
                    "province": province,
                    "service_warehouse_id": int(service_wid),
                    "reason": "INSUFFICIENT_QTY",
                    "insufficient": insufficient,
                    "considered": [int(service_wid)],
                },
                auto_commit=False,
            )
        except Exception:
            pass
        return {
            "status": "FULFILLMENT_BLOCKED",
            "service_warehouse_id": int(service_wid),
            "province": province,
            "reason": "INSUFFICIENT_QTY",
            "considered": [int(service_wid)],
        }

    # READY：写入履约字段，并设置 orders.warehouse_id（让 reserve 主线继续）
    await session.execute(
        text(
            """
            UPDATE orders
               SET warehouse_id = :wid,
                   service_warehouse_id = :wid,
                   fulfillment_warehouse_id = :wid,
                   fulfillment_status = 'READY_TO_FULFILL',
                   blocked_reasons = NULL,
                   blocked_detail = NULL
             WHERE id = :oid
            """
        ),
        {"wid": int(service_wid), "oid": int(order_id)},
    )

    try:
        await AuditEventWriter.write(
            session,
            flow="OUTBOUND",
            event="WAREHOUSE_ROUTED",
            ref=order_ref,
            trace_id=trace_id,
            meta={
                "platform": plat_norm,
                "shop": shop_id,
                "warehouse_id": int(service_wid),
                "province": province,
                "reason": "service_province_hit",
                "considered": [int(service_wid)],
            },
            auto_commit=False,
        )
    except Exception:
        pass

    return {
        "status": "READY_TO_FULFILL",
        "warehouse_id": int(service_wid),
        "service_warehouse_id": int(service_wid),
        "province": province,
        "reason": "service_province_hit",
        "considered": [int(service_wid)],
    }
