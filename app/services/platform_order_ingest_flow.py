# app/services/platform_order_ingest_flow.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService
from app.services.platform_order_fact_service import upsert_platform_order_lines
from app.services.platform_order_ingest_evidence import attach_reason_and_actions
from app.services.platform_order_ingest_universe_guard import enforce_no_test_items_in_non_test_shop, extract_item_ids_from_items_payload
from app.services.platform_order_resolve_service import (
    ResolvedLine,
    load_items_brief,
    norm_platform,
    norm_shop_id,
    resolve_platform_lines_to_items,
)

# 现有工程里这些 helper 仍在 routers 目录下并被多处复用。
# 先把“编排唯一真相”收敛到 Flow，再考虑更彻底的分层搬迁。
from app.api.routers.platform_orders_ingest_helpers import (  # noqa: WPS433
    build_items_payload,
    load_order_fulfillment_brief,
)
from app.api.routers.platform_orders_ingest_risk import (  # noqa: WPS433
    aggregate_risk_from_unresolved,
)
from app.api.routers.platform_orders_shared import (  # noqa: WPS433
    build_items_payload_from_item_qty_map,
)


class PlatformOrderIngestFlow:
    """
    平台订单接入编排流（唯一真相）：

    - 负责：事实写入、解析、风险聚合、items payload 构造、落单、读取履约简报
    - 不负责：HTTP 校验、FastAPI 异常翻译、Request.json()
    - 不负责：事务提交/回滚（由调用方 router 控制）
    """

    # -------- Common helpers -------- #

    @staticmethod
    async def resolve_fact_lines(
        session: AsyncSession,
        *,
        platform: str,
        store_id: int,
        lines: List[Dict[str, Any]],
    ) -> Tuple[List[ResolvedLine], List[Dict[str, Any]], Dict[int, int]]:
        plat = norm_platform(platform)
        sid = int(store_id)
        return await resolve_platform_lines_to_items(
            session,
            platform=plat,
            store_id=sid,
            lines=lines,
        )

    @staticmethod
    async def build_items_payload_from_item_qty_map(
        session: AsyncSession,
        *,
        store_id: int,
        item_qty_map: Dict[int, int],
        source: str,
        extras: Optional[Dict[str, Any]] = None,
    ) -> Sequence[Mapping[str, Any]]:
        item_ids = sorted(item_qty_map.keys())
        items_brief = await load_items_brief(session, item_ids=item_ids)
        return build_items_payload_from_item_qty_map(
            item_qty_map=item_qty_map,
            items_brief=items_brief,
            store_id=int(store_id),
            source=source,
            extras=extras,
        )

    @staticmethod
    async def resolve_fact_lines_and_build_items_payload(
        session: AsyncSession,
        *,
        platform: str,
        store_id: int,
        lines: List[Dict[str, Any]],
        source: str,
        extras: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[ResolvedLine], List[Dict[str, Any]], Dict[int, int], Sequence[Mapping[str, Any]]]:
        resolved_lines, unresolved, item_qty_map = await PlatformOrderIngestFlow.resolve_fact_lines(
            session,
            platform=platform,
            store_id=store_id,
            lines=lines,
        )
        items_payload: Sequence[Mapping[str, Any]] = ()
        if item_qty_map:
            items_payload = await PlatformOrderIngestFlow.build_items_payload_from_item_qty_map(
                session,
                store_id=store_id,
                item_qty_map=item_qty_map,
                source=source,
                extras=extras,
            )
        return resolved_lines, unresolved, item_qty_map, items_payload

    # -------- Main flow: from platform lines (ingest/devtools/order-sim) -------- #

    @staticmethod
    async def run_from_platform_lines(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        store_id: int,
        ext_order_no: str,
        occurred_at: Optional[datetime],
        buyer_name: Optional[str],
        buyer_phone: Optional[str],
        address: Mapping[str, str] | None,
        raw_lines: List[Dict[str, Any]],
        raw_payload: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        source: str = "platform-orders/ingest",
        extras: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        plat = norm_platform(platform)
        sid = norm_shop_id(shop_id)
        store_id_int = int(store_id)

        ext = str(ext_order_no or "").strip()
        if not ext:
            raise ValueError("ext_order_no is required")

        facts_written = await upsert_platform_order_lines(
            session,
            platform=plat,
            shop_id=sid,
            store_id=store_id_int,
            ext_order_no=ext,
            lines=raw_lines,
            raw_payload=raw_payload,
        )

        resolved_lines, unresolved, item_qty_map = await resolve_platform_lines_to_items(
            session,
            platform=plat,
            store_id=store_id_int,
            lines=raw_lines,
        )

        risk_flags, risk_level, risk_reason = aggregate_risk_from_unresolved(unresolved)
        allow_manual_continue = bool(unresolved)

        # 未解析出任何 items：只返回事实+解析证据（不落单）
        if not item_qty_map:
            out = {
                "status": "UNRESOLVED",
                "id": None,
                "ref": f"ORD:{plat}:{sid}:{ext}",
                "store_id": store_id_int,
                "resolved": [r.__dict__ for r in resolved_lines],
                "unresolved": unresolved,
                "facts_written": facts_written,
                "fulfillment_status": None,
                "blocked_reasons": None,
                "allow_manual_continue": allow_manual_continue,
                "risk_flags": risk_flags,
                "risk_level": risk_level,
                "risk_reason": risk_reason,
            }
            return attach_reason_and_actions(out, platform=plat, shop_id=sid)

        item_ids = sorted(item_qty_map.keys())

        # ✅ 宇宙边界兜底：非 TEST 商铺禁止出现测试商品（DEFAULT Test Set）
        await enforce_no_test_items_in_non_test_shop(
            session,
            shop_id=sid,
            store_id=store_id_int,
            item_ids=item_ids,
            source=source,
        )

        items_brief = await load_items_brief(session, item_ids=item_ids)

        items_payload = build_items_payload(
            item_qty_map=item_qty_map,
            items_brief=items_brief,
            store_id=store_id_int,
            source=source,
        )

        merged_extras: Dict[str, Any] = {"store_id": store_id_int, "source": source}
        if extras:
            merged_extras.update(dict(extras))

        r = await OrderService.ingest(
            session,
            platform=plat,
            shop_id=sid,
            ext_order_no=ext,
            occurred_at=occurred_at,
            buyer_name=buyer_name,
            buyer_phone=buyer_phone,
            order_amount=0.0,
            pay_amount=0.0,
            items=items_payload,
            address=address,
            extras=merged_extras,
            trace_id=trace_id,
        )

        oid = int(r.get("id") or 0) if r.get("id") is not None else None
        ref = str(r.get("ref") or f"ORD:{plat}:{sid}:{ext}")
        status = str(r.get("status") or "OK")

        fulfillment_status = None
        blocked_reasons = None
        if oid is not None:
            fulfillment_status, blocked_reasons = await load_order_fulfillment_brief(session, order_id=oid)

        out = {
            "status": status,
            "id": oid,
            "ref": ref,
            "store_id": store_id_int,
            "resolved": [r.__dict__ for r in resolved_lines],
            "unresolved": unresolved,
            "facts_written": facts_written,
            "fulfillment_status": fulfillment_status,
            "blocked_reasons": blocked_reasons,
            "allow_manual_continue": allow_manual_continue,
            "risk_flags": risk_flags,
            "risk_level": risk_level,
            "risk_reason": risk_reason,
        }
        return attach_reason_and_actions(out, platform=plat, shop_id=sid)

    # -------- Tail flow: from items_payload (replay/confirm-create) -------- #

    @staticmethod
    async def run_tail_from_items_payload(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        store_id: Optional[int],
        ext_order_no: str,
        occurred_at: Optional[datetime],
        buyer_name: Optional[str],
        buyer_phone: Optional[str],
        address: Mapping[str, str] | None,
        items_payload: Sequence[Mapping[str, Any]],
        trace_id: Optional[str] = None,
        source: str = "platform-orders/ingest",
        extras: Optional[Mapping[str, Any]] = None,
        resolved: Optional[List[Dict[str, Any]]] = None,
        unresolved: Optional[List[Dict[str, Any]]] = None,
        facts_written: int = 0,
        allow_manual_continue: Optional[bool] = None,
        risk_flags: Optional[List[str]] = None,
        risk_level: Optional[str] = None,
        risk_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        plat = norm_platform(platform)
        sid = norm_shop_id(shop_id)
        ext = str(ext_order_no or "").strip()
        if not ext:
            raise ValueError("ext_order_no is required")

        store_id_out = int(store_id) if store_id is not None else None

        # ✅ 宇宙边界兜底：tail/replay/confirm-create 也不能把测试商品写进非 TEST 商铺
        item_ids = extract_item_ids_from_items_payload(items_payload)
        await enforce_no_test_items_in_non_test_shop(
            session,
            shop_id=sid,
            store_id=store_id_out,
            item_ids=item_ids,
            source=source,
        )

        merged_extras: Dict[str, Any] = {"source": source}
        if store_id_out is not None:
            merged_extras["store_id"] = store_id_out
        if extras:
            merged_extras.update(dict(extras))

        r = await OrderService.ingest(
            session,
            platform=plat,
            shop_id=sid,
            ext_order_no=ext,
            occurred_at=occurred_at,
            buyer_name=buyer_name,
            buyer_phone=buyer_phone,
            order_amount=0.0,
            pay_amount=0.0,
            items=items_payload,
            address=address,
            extras=merged_extras,
            trace_id=trace_id,
        )

        oid = int(r.get("id") or 0) if r.get("id") is not None else None
        ref = str(r.get("ref") or f"ORD:{plat}:{sid}:{ext}")
        status = str(r.get("status") or "OK")

        fulfillment_status = None
        blocked_reasons = None
        if oid is not None:
            fulfillment_status, blocked_reasons = await load_order_fulfillment_brief(session, order_id=oid)

        resolved_out = list(resolved or [])
        unresolved_out = list(unresolved or [])
        allow_manual_continue_out = bool(unresolved_out) if allow_manual_continue is None else bool(allow_manual_continue)

        out = {
            "status": status,
            "id": oid,
            "ref": ref,
            "store_id": store_id_out,
            "resolved": resolved_out,
            "unresolved": unresolved_out,
            "facts_written": int(facts_written or 0),
            "fulfillment_status": fulfillment_status,
            "blocked_reasons": blocked_reasons,
            "allow_manual_continue": allow_manual_continue_out,
            "risk_flags": list(risk_flags or []),
            "risk_level": risk_level,
            "risk_reason": risk_reason,
        }
        return attach_reason_and_actions(out, platform=plat, shop_id=sid)
