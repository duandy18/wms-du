# app/api/routers/stores_routes_order_sim_generate.py
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.api.routers.stores_order_sim_repo import get_cart_lines, get_merchant_lines, load_store_platform_shop_id
from app.api.routers.stores_order_sim_service import (
    build_ext_order_no,
    build_raw_lines_from_facts,
    choose_address_from_cart,
    choose_buyer_from_cart,
)
from app.api.routers.stores_routes_bindings_helpers import check_store_perm, ensure_store_exists
from app.api.routers.stores_routes_order_sim_gate import enforce_order_sim_test_shop_gate, enforce_order_sim_test_store_gate
from app.api.routers.stores_routes_order_sim_schemas import (
    OrderSimGenerateOrderIn,
    OrderSimGenerateOrderOut,
    OrderSimPreviewOrderIn,
    OrderSimPreviewOrderOut,
)
from app.api.routers.stores_routes_order_sim_testset_guard import assert_order_sim_all_items_in_test_set
from app.db.deps import get_db
from app.services.platform_order_ingest_flow import PlatformOrderIngestFlow


def _sanitize_preview_ingest_result(out_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    预览（dry-run）必须“去误导化”：
    - dry_run=true
    - id=None（不宣称已生成订单）
    - facts_written=0（不宣称已写事实）
    """
    out = dict(out_dict or {})
    out["dry_run"] = True
    out["id"] = None
    out["facts_written"] = 0
    return out


def register(router: APIRouter) -> None:
    @router.post(
        "/stores/{store_id}/order-sim/preview-order",
        response_model=OrderSimPreviewOrderOut,
    )
    async def preview_order_sim_order(
        store_id: int = Path(..., ge=1),
        payload: OrderSimPreviewOrderIn = Body(...),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        enforce_order_sim_test_store_gate(store_id=int(store_id))
        check_store_perm(db, current_user, ["config.store.write"])
        await ensure_store_exists(session, store_id)

        platform, shop_id = await load_store_platform_shop_id(session, store_id=int(store_id))
        enforce_order_sim_test_shop_gate(shop_id=str(shop_id))

        merchant_items = await get_merchant_lines(session, store_id=int(store_id))
        cart_items = await get_cart_lines(session, store_id=int(store_id))

        raw_lines, selected = build_raw_lines_from_facts(merchant_items=merchant_items, cart_items=cart_items)
        address = choose_address_from_cart(selected)
        if address is None:
            raise HTTPException(status_code=422, detail="请先在购物车填写收货地址（receiver_name/province/city/detail/receiver_phone 等）")

        buyer_name, buyer_phone = choose_buyer_from_cart(selected)

        ext_order_no = build_ext_order_no(
            platform=platform,
            store_id=int(store_id),
            idempotency_key=payload.idempotency_key,
        )

        # ✅ preview：用 SAVEPOINT 执行 flow，但最终 rollback，保证不落库
        tx = await session.begin_nested()
        try:
            out_dict = await PlatformOrderIngestFlow.run_from_platform_lines(
                session,
                platform=platform,
                shop_id=shop_id,
                store_id=int(store_id),
                ext_order_no=ext_order_no,
                occurred_at=None,
                buyer_name=buyer_name,
                buyer_phone=buyer_phone,
                address=address,
                raw_lines=raw_lines,
                raw_payload={
                    "_order_sim": True,
                    "_preview": True,
                    "source": "stores/order-sim/preview-order",
                    "store_id": int(store_id),
                },
                trace_id=None,
                source="stores/order-sim/preview-order",
                extras={
                    "store_id": int(store_id),
                    "source": "stores/order-sim/preview-order",
                    "_preview": True,
                },
            )

            await assert_order_sim_all_items_in_test_set(
                session=session,
                out_dict=out_dict if isinstance(out_dict, dict) else {},
                platform=platform,
                shop_id=str(shop_id),
                store_id=int(store_id),
            )
        finally:
            await tx.rollback()

        data = {
            "preview": {
                "dry_run": True,
                "store_id": int(store_id),
                "platform": platform,
                "shop_id": str(shop_id),
                "ext_order_no": ext_order_no,
                "buyer_name": buyer_name,
                "buyer_phone": buyer_phone,
                "address": address,
                "raw_lines": raw_lines,
            },
            "ingest_result": _sanitize_preview_ingest_result(out_dict if isinstance(out_dict, dict) else {}),
        }
        return OrderSimPreviewOrderOut(ok=True, data=data)

    @router.post(
        "/stores/{store_id}/order-sim/generate-order",
        response_model=OrderSimGenerateOrderOut,
    )
    async def generate_order_sim_order(
        store_id: int = Path(..., ge=1),
        payload: OrderSimGenerateOrderIn = Body(...),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        enforce_order_sim_test_store_gate(store_id=int(store_id))
        check_store_perm(db, current_user, ["config.store.write"])
        await ensure_store_exists(session, store_id)

        platform, shop_id = await load_store_platform_shop_id(session, store_id=int(store_id))
        enforce_order_sim_test_shop_gate(shop_id=str(shop_id))

        merchant_items = await get_merchant_lines(session, store_id=int(store_id))
        cart_items = await get_cart_lines(session, store_id=int(store_id))

        raw_lines, selected = build_raw_lines_from_facts(merchant_items=merchant_items, cart_items=cart_items)
        address = choose_address_from_cart(selected)
        if address is None:
            raise HTTPException(status_code=422, detail="请先在购物车填写收货地址（receiver_name/province/city/detail/receiver_phone 等）")

        buyer_name, buyer_phone = choose_buyer_from_cart(selected)

        ext_order_no = build_ext_order_no(
            platform=platform,
            store_id=int(store_id),
            idempotency_key=payload.idempotency_key,
        )

        out_dict = await PlatformOrderIngestFlow.run_from_platform_lines(
            session,
            platform=platform,
            shop_id=shop_id,
            store_id=int(store_id),
            ext_order_no=ext_order_no,
            occurred_at=None,
            buyer_name=buyer_name,
            buyer_phone=buyer_phone,
            address=address,
            raw_lines=raw_lines,
            raw_payload={
                "_order_sim": True,
                "source": "stores/order-sim/generate-order",
                "store_id": int(store_id),
            },
            trace_id=None,
            source="stores/order-sim/generate-order",
            extras={
                "store_id": int(store_id),
                "source": "stores/order-sim/generate-order",
            },
        )

        try:
            await assert_order_sim_all_items_in_test_set(
                session=session,
                out_dict=out_dict if isinstance(out_dict, dict) else {},
                platform=platform,
                shop_id=str(shop_id),
                store_id=int(store_id),
            )
        except HTTPException:
            await session.rollback()
            raise

        await session.commit()
        return OrderSimGenerateOrderOut(ok=True, data=out_dict)
