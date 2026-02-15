# app/api/routers/stores_routes_order_sim_cart.py
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.api.routers.stores_order_sim_repo import get_cart_lines, load_store_platform_shop_id, upsert_cart_line
from app.api.routers.stores_routes_bindings_helpers import check_store_perm, ensure_store_exists
from app.api.routers.stores_routes_order_sim_gate import enforce_order_sim_test_shop_gate, enforce_order_sim_test_store_gate
from app.api.routers.stores_order_sim_service import norm_row_no
from app.api.routers.stores_routes_order_sim_schemas import OrderSimCartGetOut, OrderSimCartPutIn, OrderSimCartPutOut
from app.db.deps import get_db
from app.services.order_ingest_routing.normalize import normalize_province_name


def _norm_str(v) -> str:
    if v is None:
        return ""
    return str(v).replace("\u3000", " ").strip()


def register(router: APIRouter) -> None:
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
        enforce_order_sim_test_store_gate(store_id=int(store_id))
        check_store_perm(db, current_user, ["config.store.read"])
        await ensure_store_exists(session, store_id)

        _, shop_id = await load_store_platform_shop_id(session, store_id=int(store_id))
        enforce_order_sim_test_shop_gate(shop_id=str(shop_id))

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
        enforce_order_sim_test_store_gate(store_id=int(store_id))
        check_store_perm(db, current_user, ["config.store.write"])
        await ensure_store_exists(session, store_id)

        _, shop_id = await load_store_platform_shop_id(session, store_id=int(store_id))
        enforce_order_sim_test_shop_gate(shop_id=str(shop_id))

        seen: set[int] = set()
        for it in payload.items or []:
            rn = norm_row_no(it.row_no)
            if rn in seen:
                raise HTTPException(status_code=422, detail=f"row_no 重复：{rn}")
            seen.add(rn)

            prov_norm = normalize_province_name(_norm_str(it.province)) if _norm_str(it.province) else None

            await upsert_cart_line(
                session,
                store_id=store_id,
                row_no=rn,
                checked=bool(it.checked),
                qty=int(it.qty or 0),
                receiver_name=_norm_str(it.receiver_name) or None,
                receiver_phone=_norm_str(it.receiver_phone) or None,
                province=prov_norm,
                city=_norm_str(it.city) or None,
                district=_norm_str(it.district) or None,
                detail=_norm_str(it.detail) or None,
                zipcode=_norm_str(it.zipcode) or None,
                if_version=it.if_version,
            )

        await session.commit()
        items = await get_cart_lines(session, store_id=store_id)
        return OrderSimCartPutOut(ok=True, data={"store_id": int(store_id), "items": items})
