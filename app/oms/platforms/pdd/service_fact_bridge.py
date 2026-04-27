from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.oms.repos.platform_order_fact_service import upsert_platform_order_lines


class PddFactBridgeServiceError(Exception):
    """PDD 专表事实桥接到 OMS 归一事实行异常。"""


@dataclass(frozen=True)
class PddFactBridgeResult:
    platform: str
    store_id: int
    store_code: str
    pdd_order_id: int
    ext_order_no: str
    lines_count: int
    facts_written: int


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return value


def _build_spec(*, platform_goods_id: Any, platform_sku_id: Any) -> str | None:
    parts: list[str] = []
    if platform_goods_id:
        parts.append(f"goods_id:{platform_goods_id}")
    if platform_sku_id:
        parts.append(f"sku_id:{platform_sku_id}")
    return " / ".join(parts) if parts else None


class PddFactBridgeService:
    """
    PDD 专表事实 → OMS 归一事实行桥接。

    边界：
    - 读取 pdd_orders / pdd_order_items；
    - 转换为 platform_order_lines 所需 raw_lines；
    - 调用 upsert_platform_order_lines；
    - 不解析 FSKU；
    - 不建内部 orders/order_items；
    - 不写 pdd_order_order_mappings；
    - 不触碰 finance。
    """

    async def bridge_one_order(
        self,
        session: AsyncSession,
        *,
        pdd_order_id: int,
    ) -> PddFactBridgeResult:
        oid = int(pdd_order_id)
        if oid <= 0:
            raise PddFactBridgeServiceError("pdd_order_id must be positive")

        head = (
            await session.execute(
                text(
                    """
                    SELECT
                      po.id,
                      po.store_id,
                      po.order_sn,
                      po.raw_detail_payload,
                      s.store_code
                    FROM pdd_orders po
                    JOIN stores s ON s.id = po.store_id
                    WHERE po.id = :pdd_order_id
                      AND upper(s.platform) = 'PDD'
                    LIMIT 1
                    """
                ),
                {"pdd_order_id": oid},
            )
        ).mappings().first()

        if not head:
            raise PddFactBridgeServiceError(f"pdd order not found: pdd_order_id={oid}")

        rows = (
            await session.execute(
                text(
                    """
                    SELECT
                      id,
                      pdd_order_id,
                      order_sn,
                      platform_goods_id,
                      platform_sku_id,
                      outer_id,
                      goods_name,
                      goods_count,
                      goods_price,
                      raw_item_payload
                    FROM pdd_order_items
                    WHERE pdd_order_id = :pdd_order_id
                    ORDER BY id ASC
                    """
                ),
                {"pdd_order_id": oid},
            )
        ).mappings().all()

        raw_lines: List[Dict[str, Any]] = []
        for idx, item in enumerate(rows, start=1):
            goods_count = int(item.get("goods_count") or 0)
            qty = goods_count if goods_count > 0 else 1
            platform_goods_id = item.get("platform_goods_id")
            platform_sku_id = item.get("platform_sku_id")
            outer_id = item.get("outer_id")

            extras = {
                "source": "pdd_order_items",
                "pdd_order_id": int(item["pdd_order_id"]),
                "pdd_order_item_id": int(item["id"]),
                "platform_goods_id": platform_goods_id,
                "platform_sku_id": platform_sku_id,
                "outer_id": outer_id,
                "goods_price": _json_safe(item.get("goods_price")),
                "raw_item_payload": item.get("raw_item_payload"),
            }

            raw_lines.append(
                {
                    "line_no": idx,
                    "filled_code": str(outer_id).strip() if outer_id else None,
                    "qty": qty,
                    "title": item.get("goods_name"),
                    "spec": _build_spec(
                        platform_goods_id=platform_goods_id,
                        platform_sku_id=platform_sku_id,
                    ),
                    "extras": extras,
                }
            )

        facts_written = await upsert_platform_order_lines(
            session,
            platform="PDD",
            store_code=str(head["store_code"]),
            store_id=int(head["store_id"]),
            ext_order_no=str(head["order_sn"]),
            lines=raw_lines,
            raw_payload=head.get("raw_detail_payload") or {},
        )

        return PddFactBridgeResult(
            platform="PDD",
            store_id=int(head["store_id"]),
            store_code=str(head["store_code"]),
            pdd_order_id=oid,
            ext_order_no=str(head["order_sn"]),
            lines_count=len(raw_lines),
            facts_written=int(facts_written),
        )
