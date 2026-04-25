# app/tms/shipment/routes_waybill_config.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.tms.permissions import check_config_perm

from .contracts_waybill_config import (
    WaybillConfigCreateIn,
    WaybillConfigCreateOut,
    WaybillConfigDetailOut,
    WaybillConfigListOut,
    WaybillConfigUpdateIn,
    WaybillConfigUpdateOut,
)
from .repository_waybill_config import (
    create_waybill_config,
    get_waybill_config,
    list_waybill_configs,
    update_waybill_config,
)


def register(router: APIRouter) -> None:
    @router.get("/shipping-assist/settings/waybill-configs", response_model=WaybillConfigListOut)
    async def list_waybill_configs_route(
        active: Optional[bool] = Query(None),
        platform: Optional[str] = Query(None),
        shop_id: Optional[str] = Query(None),
        shipping_provider_id: Optional[int] = Query(None, ge=1),
        q: Optional[str] = Query(None),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> WaybillConfigListOut:
        check_config_perm(db, current_user, ["config.store.read"])
        data = await list_waybill_configs(
            session,
            active=active,
            platform=platform,
            shop_id=shop_id,
            shipping_provider_id=shipping_provider_id,
            q=q,
        )
        return WaybillConfigListOut(ok=True, data=data)

    @router.get("/shipping-assist/settings/waybill-configs/{config_id}", response_model=WaybillConfigDetailOut)
    async def get_waybill_config_route(
        config_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> WaybillConfigDetailOut:
        check_config_perm(db, current_user, ["config.store.read"])
        data = await get_waybill_config(session, config_id)
        if not data:
            raise HTTPException(status_code=404, detail="waybill_config not found")
        return WaybillConfigDetailOut(ok=True, data=data)

    @router.post("/shipping-assist/settings/waybill-configs", response_model=WaybillConfigCreateOut, status_code=201)
    async def create_waybill_config_route(
        payload: WaybillConfigCreateIn,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> WaybillConfigCreateOut:
        check_config_perm(db, current_user, ["config.store.write"])
        try:
            data = await create_waybill_config(
                session,
                platform=payload.platform,
                shop_id=payload.shop_id,
                shipping_provider_id=payload.shipping_provider_id,
                customer_code=payload.customer_code,
                sender_name=payload.sender_name,
                sender_mobile=payload.sender_mobile,
                sender_phone=payload.sender_phone,
                sender_province=payload.sender_province,
                sender_city=payload.sender_city,
                sender_district=payload.sender_district,
                sender_address=payload.sender_address,
                active=payload.active,
            )
            await session.commit()
            return WaybillConfigCreateOut(ok=True, data=data)
        except IntegrityError as e:
            await session.rollback()
            raise HTTPException(status_code=409, detail="waybill_config already exists or shipping_provider invalid") from e
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=422, detail=str(e)) from e

    @router.patch("/shipping-assist/settings/waybill-configs/{config_id}", response_model=WaybillConfigUpdateOut)
    async def update_waybill_config_route(
        payload: WaybillConfigUpdateIn,
        config_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> WaybillConfigUpdateOut:
        check_config_perm(db, current_user, ["config.store.write"])
        try:
            data = await update_waybill_config(
                session,
                config_id=config_id,
                platform=payload.platform,
                shop_id=payload.shop_id,
                shipping_provider_id=payload.shipping_provider_id,
                customer_code=payload.customer_code,
                sender_name=payload.sender_name,
                sender_mobile=payload.sender_mobile,
                sender_phone=payload.sender_phone,
                sender_province=payload.sender_province,
                sender_city=payload.sender_city,
                sender_district=payload.sender_district,
                sender_address=payload.sender_address,
                active=payload.active,
            )
            if not data:
                await session.rollback()
                raise HTTPException(status_code=404, detail="waybill_config not found")
            await session.commit()
            return WaybillConfigUpdateOut(ok=True, data=data)
        except IntegrityError as e:
            await session.rollback()
            raise HTTPException(status_code=409, detail="waybill_config already exists or shipping_provider invalid") from e
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=422, detail=str(e)) from e
