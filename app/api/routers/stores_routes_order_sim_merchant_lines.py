# app/api/routers/stores_routes_order_sim_merchant_lines.py
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.api.routers.stores_order_sim_bindings_repo import build_components_summary_by_filled_code, list_bound_filled_code_options
from app.api.routers.stores_order_sim_repo import get_merchant_lines, load_store_platform_shop_id, upsert_merchant_line
from app.api.routers.stores_routes_bindings_helpers import check_store_perm, ensure_store_exists
from app.api.routers.stores_routes_order_sim_gate import enforce_order_sim_test_shop_gate, enforce_order_sim_test_store_gate
from app.api.routers.stores_order_sim_service import norm_row_no
from app.api.routers.stores_routes_order_sim_schemas import (
    OrderSimFilledCodeOptionsOut,
    OrderSimMerchantLinesGetOut,
    OrderSimMerchantLinesPutIn,
    OrderSimMerchantLinesPutOut,
)
from app.db.deps import get_db


def register(router: APIRouter) -> None:
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
        enforce_order_sim_test_store_gate(store_id=int(store_id))
        check_store_perm(db, current_user, ["config.store.read"])
        await ensure_store_exists(session, store_id)

        _, shop_id = await load_store_platform_shop_id(session, store_id=int(store_id))
        enforce_order_sim_test_shop_gate(shop_id=str(shop_id))

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
        enforce_order_sim_test_store_gate(store_id=int(store_id))
        check_store_perm(db, current_user, ["config.store.read"])
        await ensure_store_exists(session, store_id)

        platform, shop_id = await load_store_platform_shop_id(session, store_id=int(store_id))
        enforce_order_sim_test_shop_gate(shop_id=str(shop_id))

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
        enforce_order_sim_test_store_gate(store_id=int(store_id))
        check_store_perm(db, current_user, ["config.store.write"])
        await ensure_store_exists(session, store_id)

        platform, shop_id = await load_store_platform_shop_id(session, store_id=int(store_id))
        enforce_order_sim_test_shop_gate(shop_id=str(shop_id))

        seen: set[int] = set()
        for it in payload.items or []:
            rn = norm_row_no(it.row_no)
            if rn in seen:
                raise HTTPException(status_code=422, detail=f"row_no 重复：{rn}")
            seen.add(rn)

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
