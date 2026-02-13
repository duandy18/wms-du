# app/api/routers/stores_routes_order_sim.py
from __future__ import annotations


from fastapi import APIRouter, Body, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.api.routers.stores_order_sim_bindings_repo import (
    build_components_summary_by_filled_code,
    list_bound_filled_code_options,
)
from app.api.routers.stores_order_sim_repo import (
    get_cart_lines,
    get_merchant_lines,
    load_store_platform_shop_id,
    upsert_cart_line,
    upsert_merchant_line,
)
from app.api.routers.stores_order_sim_service import (
    build_ext_order_no,
    build_raw_lines_from_facts,
    choose_address_from_cart,
    norm_row_no,
)
from app.api.routers.stores_routes_bindings_helpers import check_store_perm, ensure_store_exists
from app.api.routers.stores_routes_order_sim_schemas import (
    OrderSimCartGetOut,
    OrderSimCartPutIn,
    OrderSimCartPutOut,
    OrderSimFilledCodeOptionsOut,
    OrderSimGenerateOrderIn,
    OrderSimGenerateOrderOut,
    OrderSimMerchantLinesGetOut,
    OrderSimMerchantLinesPutIn,
    OrderSimMerchantLinesPutOut,
)
from app.db.deps import get_db
from app.services.platform_order_ingest_flow import PlatformOrderIngestFlow


def register(router: APIRouter) -> None:
    # ---------------- merchant lines ----------------

    @router.get(
        "/stores/{store_id}/order-sim/merchant-lines",
        response_model=OrderSimMerchantLinesGetOut,
    )
    async def get_order_sim_merchant_lines(
        store_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        check_store_perm(db, current_user, ["config.store.read"])
        await ensure_store_exists(session, store_id)
        items = await get_merchant_lines(session, store_id=store_id)
        return OrderSimMerchantLinesGetOut(ok=True, data={"store_id": int(store_id), "items": items})

    @router.get(
        "/stores/{store_id}/order-sim/filled-code-options",
        response_model=OrderSimFilledCodeOptionsOut,
    )
    async def get_order_sim_filled_code_options(
        store_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        check_store_perm(db, current_user, ["config.store.read"])
        await ensure_store_exists(session, store_id)

        platform, shop_id = await load_store_platform_shop_id(session, store_id=int(store_id))
        items = await list_bound_filled_code_options(session, platform=platform, shop_id=shop_id)
        return OrderSimFilledCodeOptionsOut(ok=True, data={"items": items})

    @router.put(
        "/stores/{store_id}/order-sim/merchant-lines",
        response_model=OrderSimMerchantLinesPutOut,
    )
    async def put_order_sim_merchant_lines(
        store_id: int = Path(..., ge=1),
        payload: OrderSimMerchantLinesPutIn = Body(...),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        check_store_perm(db, current_user, ["config.store.write"])
        await ensure_store_exists(session, store_id)

        platform, shop_id = await load_store_platform_shop_id(session, store_id=int(store_id))

        seen: set[int] = set()
        for it in payload.items or []:
            rn = norm_row_no(it.row_no)
            if rn in seen:
                raise HTTPException(status_code=422, detail=f"row_no 重复：{rn}")
            seen.add(rn)

            # ✅ spec 不可修改：忽略前端传入 spec，后端按绑定事实重算
            spec_summary = None
            if (it.filled_code or "").strip():
                spec_summary = await build_components_summary_by_filled_code(
                    session,
                    platform=platform,
                    shop_id=shop_id,
                    filled_code=str(it.filled_code).strip(),
                )

            await upsert_merchant_line(
                session,
                store_id=store_id,
                row_no=rn,
                filled_code=it.filled_code,
                title=it.title,
                spec=spec_summary,
                if_version=it.if_version,
            )

        await session.commit()
        items = await get_merchant_lines(session, store_id=store_id)
        return OrderSimMerchantLinesPutOut(ok=True, data={"store_id": int(store_id), "items": items})

    # ---------------- cart ----------------

    @router.get(
        "/stores/{store_id}/order-sim/cart",
        response_model=OrderSimCartGetOut,
    )
    async def get_order_sim_cart(
        store_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        check_store_perm(db, current_user, ["config.store.read"])
        await ensure_store_exists(session, store_id)
        items = await get_cart_lines(session, store_id=store_id)
        return OrderSimCartGetOut(ok=True, data={"store_id": int(store_id), "items": items})

    @router.put(
        "/stores/{store_id}/order-sim/cart",
        response_model=OrderSimCartPutOut,
    )
    async def put_order_sim_cart(
        store_id: int = Path(..., ge=1),
        payload: OrderSimCartPutIn = Body(...),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        check_store_perm(db, current_user, ["config.store.write"])
        await ensure_store_exists(session, store_id)

        seen: set[int] = set()
        for it in payload.items or []:
            rn = norm_row_no(it.row_no)
            if rn in seen:
                raise HTTPException(status_code=422, detail=f"row_no 重复：{rn}")
            seen.add(rn)

            await upsert_cart_line(
                session,
                store_id=store_id,
                row_no=rn,
                checked=bool(it.checked),
                qty=int(it.qty or 0),
                province=it.province,
                city=it.city,
                if_version=it.if_version,
            )

        await session.commit()
        items = await get_cart_lines(session, store_id=store_id)
        return OrderSimCartPutOut(ok=True, data={"store_id": int(store_id), "items": items})

    # ---------------- generate order ----------------

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
        check_store_perm(db, current_user, ["config.store.write"])
        await ensure_store_exists(session, store_id)

        platform, shop_id = await load_store_platform_shop_id(session, store_id=int(store_id))
        merchant_items = await get_merchant_lines(session, store_id=int(store_id))
        cart_items = await get_cart_lines(session, store_id=int(store_id))

        raw_lines, selected = build_raw_lines_from_facts(
            merchant_items=merchant_items,
            cart_items=cart_items,
        )
        address = choose_address_from_cart(selected)

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
            buyer_name=None,
            buyer_phone=None,
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

        await session.commit()
        return OrderSimGenerateOrderOut(ok=True, data=out_dict)
