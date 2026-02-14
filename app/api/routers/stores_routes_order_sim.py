# app/api/routers/stores_routes_order_sim.py
from __future__ import annotations

import os

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.api.problem import make_problem
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
from app.services.item_test_set_service import ItemTestSetService
from app.services.order_ingest_routing.normalize import normalize_province_name
from app.services.platform_order_ingest_flow import PlatformOrderIngestFlow


def _norm_str(v) -> str:
    if v is None:
        return ""
    return str(v).replace("\u3000", " ").strip()


def _get_order_sim_test_store_id() -> int | None:
    raw = (os.getenv("ORDER_SIM_TEST_STORE_ID") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except Exception:
        return None


def _enforce_order_sim_test_store_gate(*, store_id: int) -> None:
    tid = _get_order_sim_test_store_id()
    if tid is None:
        return
    if int(store_id) != int(tid):
        raise HTTPException(
            status_code=403,
            detail=make_problem(
                status_code=403,
                error_code="forbidden",
                message="order-sim 已启用测试商铺门禁：仅允许 TEST store_id 访问",
                context={"store_id": int(store_id), "allowed_test_store_id": int(tid)},
            ),
        )


def _get_test_shop_id() -> str | None:
    s = (os.getenv("TEST_SHOP_ID") or "").strip()
    return s or None


def _enforce_order_sim_test_shop_gate(*, shop_id: str) -> None:
    """
    可选：当 TEST_SHOP_ID 设置后，order-sim 入口只能用于该测试商铺。
    """
    tid = _get_test_shop_id()
    if tid is None:
        return
    if str(shop_id) != tid:
        raise HTTPException(
            status_code=403,
            detail=make_problem(
                status_code=403,
                error_code="forbidden",
                message="order-sim 已启用测试商铺门禁：仅允许 TEST shop_id 访问",
                context={"shop_id": str(shop_id), "allowed_test_shop_id": str(tid)},
            ),
        )


def _extract_expanded_item_ids(out_dict: dict) -> list[int]:
    ids: set[int] = set()
    resolved = out_dict.get("resolved")
    if not isinstance(resolved, list):
        return []
    for r in resolved:
        if not isinstance(r, dict):
            continue
        exp = r.get("expanded_items")
        if not isinstance(exp, list):
            continue
        for it in exp:
            if not isinstance(it, dict):
                continue
            v = it.get("item_id")
            try:
                if v is None:
                    continue
                ids.add(int(v))
            except Exception:
                continue
    return sorted(ids)


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
        _enforce_order_sim_test_store_gate(store_id=int(store_id))
        check_store_perm(db, current_user, ["config.store.read"])
        await ensure_store_exists(session, store_id)

        _, shop_id = await load_store_platform_shop_id(session, store_id=int(store_id))
        _enforce_order_sim_test_shop_gate(shop_id=str(shop_id))

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
        _enforce_order_sim_test_store_gate(store_id=int(store_id))
        check_store_perm(db, current_user, ["config.store.read"])
        await ensure_store_exists(session, store_id)

        platform, shop_id = await load_store_platform_shop_id(session, store_id=int(store_id))
        _enforce_order_sim_test_shop_gate(shop_id=str(shop_id))

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
        _enforce_order_sim_test_store_gate(store_id=int(store_id))
        check_store_perm(db, current_user, ["config.store.write"])
        await ensure_store_exists(session, store_id)

        platform, shop_id = await load_store_platform_shop_id(session, store_id=int(store_id))
        _enforce_order_sim_test_shop_gate(shop_id=str(shop_id))

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
        _enforce_order_sim_test_store_gate(store_id=int(store_id))
        check_store_perm(db, current_user, ["config.store.read"])
        await ensure_store_exists(session, store_id)

        _, shop_id = await load_store_platform_shop_id(session, store_id=int(store_id))
        _enforce_order_sim_test_shop_gate(shop_id=str(shop_id))

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
        _enforce_order_sim_test_store_gate(store_id=int(store_id))
        check_store_perm(db, current_user, ["config.store.write"])
        await ensure_store_exists(session, store_id)

        _, shop_id = await load_store_platform_shop_id(session, store_id=int(store_id))
        _enforce_order_sim_test_shop_gate(shop_id=str(shop_id))

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
        _enforce_order_sim_test_store_gate(store_id=int(store_id))
        check_store_perm(db, current_user, ["config.store.write"])
        await ensure_store_exists(session, store_id)

        platform, shop_id = await load_store_platform_shop_id(session, store_id=int(store_id))
        _enforce_order_sim_test_shop_gate(shop_id=str(shop_id))

        merchant_items = await get_merchant_lines(session, store_id=int(store_id))
        cart_items = await get_cart_lines(session, store_id=int(store_id))

        raw_lines, selected = build_raw_lines_from_facts(
            merchant_items=merchant_items,
            cart_items=cart_items,
        )
        address = choose_address_from_cart(selected)
        if address is None:
            raise HTTPException(status_code=422, detail="请先在购物车填写收货地址（province/city/detail/receiver_phone 等）")

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

        # ✅ 测试域硬隔离护栏：order-sim 必须“全部是测试商品”
        try:
            item_ids = _extract_expanded_item_ids(out_dict if isinstance(out_dict, dict) else {})
            ts = ItemTestSetService(session)
            await ts.assert_items_in_test_set(item_ids=item_ids, set_code="DEFAULT")
        except ItemTestSetService.NotFound as e:
            await session.rollback()
            raise HTTPException(
                status_code=500,
                detail=make_problem(
                    status_code=500,
                    error_code="internal_error",
                    message=f"测试集合不可用：{e.message}",
                    context={"platform": platform, "shop_id": shop_id, "store_id": int(store_id), "set_code": "DEFAULT"},
                ),
            )
        except ItemTestSetService.Conflict as e:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail=make_problem(
                    status_code=409,
                    error_code="conflict",
                    message=e.message,
                    context={
                        "platform": platform,
                        "shop_id": shop_id,
                        "store_id": int(store_id),
                        "set_code": e.set_code,
                        "out_of_set_item_ids": e.out_of_set_item_ids,
                        "resolved_item_ids": _extract_expanded_item_ids(out_dict if isinstance(out_dict, dict) else {}),
                    },
                ),
            )

        await session.commit()
        return OrderSimGenerateOrderOut(ok=True, data=out_dict)
