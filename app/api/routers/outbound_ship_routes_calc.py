# app/api/routers/outbound_ship_routes_calc.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.outbound_ship_schemas import ShipCalcRequest, ShipCalcResponse, ShipQuoteOut
from app.services.ship_service import ShipService


def register(router: APIRouter) -> None:
    @router.post("/ship/calc", response_model=ShipCalcResponse)
    async def calc_shipping_quotes(
        payload: ShipCalcRequest,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),  # 只要求登录
    ) -> ShipCalcResponse:
        """
        计算发货费用矩阵（MVP）

        当前版本：
        - 使用 weight_kg + 省市区 计算费用
        """
        svc = ShipService(session)
        try:
            raw = await svc.calc_quotes(
                weight_kg=payload.weight_kg,
                province=payload.province,
                city=payload.city,
                district=payload.district,
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

        quotes = [ShipQuoteOut(**q) for q in raw.get("quotes", [])]
        return ShipCalcResponse(
            ok=raw.get("ok", True),
            weight_kg=raw["weight_kg"],
            dest=raw.get("dest"),
            quotes=quotes,
            recommended=raw.get("recommended"),
        )
