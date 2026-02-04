# app/api/routers/outbound_ship_routes_prepare.py
from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.outbound_ship_schemas import (
    CandidateWarehouseOut,
    FulfillmentMissingLineOut,
    FulfillmentScanWarehouseOut,
    ShipPrepareItem,
    ShipPrepareRequest,
    ShipPrepareResponse,
)
from app.services.outbound_ship_fulfillment_scan import aggregate_needs, scan_candidate_warehouses
from app.services.store_service import StoreService


_ALLOWED_PROVINCE_SUFFIX = ("省", "市", "自治区", "特别行政区")


def _normalize_province_soft(raw: Optional[str]) -> Optional[str]:
    p = (raw or "").strip()
    if not p:
        return None
    if len(p) > 32:
        return None
    if not any(p.endswith(s) for s in _ALLOWED_PROVINCE_SUFFIX):
        return None
    return p


async def _load_candidate_warehouses_by_province(
    session: AsyncSession,
    *,
    store_id: int,
    province: str,
) -> List[CandidateWarehouseOut]:
    """
    候选仓 = store_province_routes 命中该省的 active 规则（按 priority）：
    - 运行时强防御：
      - 仓库必须 active
      - route 引用仓必须仍属于 store_warehouse 绑定集合（避免解绑漂移）
    """
    sql = text(
        """
        SELECT
          r.warehouse_id,
          w.name AS warehouse_name,
          w.code AS warehouse_code,
          COALESCE(w.active, TRUE) AS warehouse_active,
          r.priority,
          EXISTS(
            SELECT 1 FROM store_warehouse sw
             WHERE sw.store_id = r.store_id
               AND sw.warehouse_id = r.warehouse_id
             LIMIT 1
          ) AS still_bound
        FROM store_province_routes r
        LEFT JOIN warehouses w ON w.id = r.warehouse_id
        WHERE r.store_id = :sid
          AND r.province = :prov
          AND COALESCE(r.active, TRUE) = TRUE
        ORDER BY r.priority ASC, r.id ASC
        """
    )
    rows = (await session.execute(sql, {"sid": int(store_id), "prov": str(province)})).mappings().all()

    out: List[CandidateWarehouseOut] = []
    for r in rows:
        if not bool(r.get("warehouse_active", True)):
            continue
        if not bool(r.get("still_bound", False)):
            continue
        out.append(
            CandidateWarehouseOut(
                warehouse_id=int(r["warehouse_id"]),
                warehouse_name=r.get("warehouse_name"),
                warehouse_code=r.get("warehouse_code"),
                warehouse_active=bool(r.get("warehouse_active", True)),
                priority=int(r.get("priority") or 100),
            )
        )

    # 去重（同省可能多条规则指向同仓）
    seen: set[int] = set()
    uniq: List[CandidateWarehouseOut] = []
    for x in out:
        if x.warehouse_id in seen:
            continue
        seen.add(x.warehouse_id)
        uniq.append(x)
    return uniq


def register(router: APIRouter) -> None:
    @router.post("/ship/prepare-from-order", response_model=ShipPrepareResponse)
    async def prepare_from_order(
        payload: ShipPrepareRequest,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShipPrepareResponse:
        plat = payload.platform.upper()
        shop_id = payload.shop_id
        ext_order_no = payload.ext_order_no

        sql = text(
            """
            SELECT
              o.id AS order_id,
              o.platform,
              o.shop_id,
              o.ext_order_no,
              o.trace_id,
              addr.province,
              addr.city,
              addr.district,
              addr.receiver_name,
              addr.receiver_phone,
              addr.detail AS address_detail,
              COALESCE(SUM(COALESCE(oi.qty, 0)), 0) AS total_qty,
              COALESCE(
                SUM(
                  COALESCE(oi.qty, 0) * COALESCE(it.weight_kg, 0)
                ),
                0
              ) AS estimated_weight_kg,
              COALESCE(
                json_agg(
                  json_build_object(
                    'item_id', oi.item_id,
                    'qty', COALESCE(oi.qty, 0)
                  )
                ) FILTER (WHERE oi.id IS NOT NULL),
                '[]'::json
              ) AS items
            FROM orders AS o
            LEFT JOIN order_address AS addr ON addr.order_id = o.id
            LEFT JOIN order_items AS oi ON oi.order_id = o.id
            LEFT JOIN items AS it ON it.id = oi.item_id
            WHERE o.platform = :platform
              AND o.shop_id = :shop_id
              AND o.ext_order_no = :ext_order_no
            GROUP BY
              o.id, o.platform, o.shop_id, o.ext_order_no,
              o.trace_id,
              addr.province, addr.city, addr.district,
              addr.receiver_name, addr.receiver_phone, addr.detail
            LIMIT 1
            """
        )

        row = (
            (
                await session.execute(
                    sql,
                    {
                        "platform": plat,
                        "shop_id": shop_id,
                        "ext_order_no": ext_order_no,
                    },
                )
            )
            .mappings()
            .first()
        )

        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")

        order_id = int(row["order_id"])
        province = row.get("province")
        city = row.get("city")
        district = row.get("district")
        receiver_name = row.get("receiver_name")
        receiver_phone = row.get("receiver_phone")
        address_detail = row.get("address_detail")

        total_qty = int(row["total_qty"] or 0)
        items_raw = row.get("items") or []
        items = [ShipPrepareItem(item_id=int(it["item_id"]), qty=int(it["qty"])) for it in items_raw]

        est_weight = float(row.get("estimated_weight_kg") or 0.0)
        weight_kg: Optional[float] = est_weight if est_weight > 0 else None

        trace_id = row.get("trace_id")
        ref = f"ORD:{plat}:{shop_id}:{ext_order_no}"

        # ===== store_id 对齐（店铺档案是事实入口）=====
        store_id = await StoreService.ensure_store(
            session,
            platform=plat,
            shop_id=shop_id,
            name=f"{plat}-{shop_id}",
        )

        prov_norm = _normalize_province_soft(province)
        if not prov_norm:
            return ShipPrepareResponse(
                ok=True,
                order_id=order_id,
                platform=plat,
                shop_id=shop_id,
                ext_order_no=ext_order_no,
                ref=ref,
                province=province,
                city=city,
                district=district,
                receiver_name=receiver_name,
                receiver_phone=receiver_phone,
                address_detail=address_detail,
                items=items,
                total_qty=total_qty,
                weight_kg=weight_kg,
                trace_id=trace_id,
                warehouse_id=None,
                warehouse_reason="PROVINCE_MISSING_OR_INVALID",
                candidate_warehouses=[],
                fulfillment_scan=[],
                fulfillment_status="FULFILLMENT_BLOCKED",
                blocked_reasons=["PROVINCE_MISSING_OR_INVALID"],
            )

        # ===== 候选仓：省级路由命中集合 =====
        candidates = await _load_candidate_warehouses_by_province(session, store_id=store_id, province=prov_norm)
        if not candidates:
            return ShipPrepareResponse(
                ok=True,
                order_id=order_id,
                platform=plat,
                shop_id=shop_id,
                ext_order_no=ext_order_no,
                ref=ref,
                province=province,
                city=city,
                district=district,
                receiver_name=receiver_name,
                receiver_phone=receiver_phone,
                address_detail=address_detail,
                items=items,
                total_qty=total_qty,
                weight_kg=weight_kg,
                trace_id=trace_id,
                warehouse_id=None,
                warehouse_reason="NO_PROVINCE_ROUTE_MATCH",
                candidate_warehouses=[],
                fulfillment_scan=[],
                fulfillment_status="FULFILLMENT_BLOCKED",
                blocked_reasons=["NO_PROVINCE_ROUTE_MATCH"],
            )

        # ===== 扫描：对每个候选仓做整单同仓可履约检查 =====
        needs = aggregate_needs([{"item_id": it.item_id, "qty": it.qty} for it in items])
        scan_rows = await scan_candidate_warehouses(
            session=session,
            platform=plat,
            shop_id=shop_id,
            candidate_warehouse_ids=[c.warehouse_id for c in candidates],
            needs=needs,
        )

        scan_out: List[FulfillmentScanWarehouseOut] = []
        ok_wh_ids: List[int] = []
        for r in scan_rows:
            miss = [FulfillmentMissingLineOut(**m) for m in r.to_dict().get("missing", [])]
            scan_out.append(
                FulfillmentScanWarehouseOut(
                    warehouse_id=int(r.warehouse_id),
                    status=str(r.status),
                    missing=miss,
                )
            )
            if str(r.status) == "OK":
                ok_wh_ids.append(int(r.warehouse_id))

        if not ok_wh_ids:
            # 所有候选仓都不足：明确不可履约（用于退货/取消）
            return ShipPrepareResponse(
                ok=True,
                order_id=order_id,
                platform=plat,
                shop_id=shop_id,
                ext_order_no=ext_order_no,
                ref=ref,
                province=province,
                city=city,
                district=district,
                receiver_name=receiver_name,
                receiver_phone=receiver_phone,
                address_detail=address_detail,
                items=items,
                total_qty=total_qty,
                weight_kg=weight_kg,
                trace_id=trace_id,
                warehouse_id=None,
                warehouse_reason="ALL_CANDIDATE_WAREHOUSES_INSUFFICIENT",
                candidate_warehouses=candidates,
                fulfillment_scan=scan_out,
                fulfillment_status="FULFILLMENT_BLOCKED",
                blocked_reasons=["INSUFFICIENT_QTY"],
            )

        # 有可履约仓：不预设 warehouse_id，让人选；但给出扫描证据
        return ShipPrepareResponse(
            ok=True,
            order_id=order_id,
            platform=plat,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            ref=ref,
            province=province,
            city=city,
            district=district,
            receiver_name=receiver_name,
            receiver_phone=receiver_phone,
            address_detail=address_detail,
            items=items,
            total_qty=total_qty,
            weight_kg=weight_kg,
            trace_id=trace_id,
            warehouse_id=None,
            warehouse_reason="MANUAL_SELECT_REQUIRED",
            candidate_warehouses=candidates,
            fulfillment_scan=scan_out,
            fulfillment_status="OK",
            blocked_reasons=[],
        )
