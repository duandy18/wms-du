# app/shipping_assist/shipment/service_prepare_quotes.py
# 分拆说明：
# - 本文件负责“发运准备-包裹报价”相关能力。
# - 当前只负责：
#   1) 某包裹读取候选报价
#   2) 某包裹确认报价并写回包裹事实
# - 维护约束：
#   - 报价前必须地址 ready
#   - 报价前必须存在合法 weight_kg / warehouse_id
#   - 确认报价时不信前端价格，只信 provider_id
#   - 后端重新计算并写入 selected_quote_snapshot
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shipping_assist.shipment.models.order_shipment_prepare import OrderShipmentPrepare
from app.shipping_assist.shipment.models.order_shipment_prepare_package import OrderShipmentPreparePackage
from app.shipping_assist.quote.recommend import recommend_quotes
from app.shipping_assist.quote.types import Dest
from app.shipping_assist.quote_snapshot import build_quote_snapshot


from .contracts_prepare_quotes import (
    ShipPreparePackageQuoteConfirmOut,
    ShipPreparePackageQuoteOut,
    ShipPrepareQuoteCandidateOut,
)


class ShipmentPrepareQuotesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _load_order_row(
        self,
        *,
        platform: str,
        shop_id: str,
        ext_order_no: str,
    ) -> dict[str, Any]:
        plat = (platform or "").strip().upper()
        sid = (shop_id or "").strip()
        ext = (ext_order_no or "").strip()

        if not plat or not sid or not ext:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="platform / shop_id / ext_order_no are required",
            )

        row = (
            await self.session.execute(
                text(
                    """
                    SELECT id, platform, shop_id, ext_order_no
                    FROM orders
                    WHERE platform = :platform
                      AND shop_id = :shop_id
                      AND ext_order_no = :ext_order_no
                    LIMIT 1
                    """
                ),
                {
                    "platform": plat,
                    "shop_id": sid,
                    "ext_order_no": ext,
                },
            )
        ).mappings().first()

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="order not found",
            )

        return dict(row)

    async def _load_prepare_and_package_and_address(
        self,
        *,
        platform: str,
        shop_id: str,
        ext_order_no: str,
        package_no: int,
    ) -> tuple[int, OrderShipmentPrepare, OrderShipmentPreparePackage, dict[str, Any]]:
        order_row = await self._load_order_row(
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )
        order_id = int(order_row["id"])

        prepare = await self.session.scalar(
            select(OrderShipmentPrepare).where(OrderShipmentPrepare.order_id == order_id)
        )
        if prepare is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="shipment prepare record is required before quoting",
            )

        if str(prepare.address_ready_status or "pending") != "ready":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="address_ready_status must be ready before quoting",
            )

        package = await self.session.scalar(
            select(OrderShipmentPreparePackage).where(
                OrderShipmentPreparePackage.order_id == order_id,
                OrderShipmentPreparePackage.package_no == int(package_no),
            )
        )
        if package is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"package_no={int(package_no)} not found",
            )

        if package.weight_kg is None or float(package.weight_kg) <= 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="package weight_kg is required before quoting",
            )

        if package.warehouse_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="package warehouse_id is required before quoting",
            )

        address_row = (
            await self.session.execute(
                text(
                    """
                    SELECT province, city, district, detail
                    FROM order_address
                    WHERE order_id = :order_id
                    LIMIT 1
                    """
                ),
                {"order_id": order_id},
            )
        ).mappings().first()

        if address_row is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="order_address is required before quoting",
            )

        return order_id, prepare, package, dict(address_row)

    async def _recommend_package_quotes(
        self,
        *,
        warehouse_id: int,
        weight_kg: float,
        province: str | None,
        city: str | None,
        district: str | None,
        provider_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        def _run(sync_session):
            return recommend_quotes(
                db=sync_session,
                provider_ids=provider_ids,
                warehouse_id=int(warehouse_id),
                dest=Dest(
                    province=province,
                    city=city,
                    district=district,
                ),
                real_weight_kg=float(weight_kg),
                dims_cm=None,
                flags=[],
                max_results=10,
            )

        return await self.session.run_sync(_run)

    async def quote_prepare_package(
        self,
        *,
        platform: str,
        shop_id: str,
        ext_order_no: str,
        package_no: int,
    ) -> ShipPreparePackageQuoteOut:
        _, _, package, address = await self._load_prepare_and_package_and_address(
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            package_no=package_no,
        )

        warehouse_id = int(package.warehouse_id)
        weight_kg = float(package.weight_kg)
        province = address.get("province")
        city = address.get("city")
        district = address.get("district")

        raw = await self._recommend_package_quotes(
            warehouse_id=warehouse_id,
            weight_kg=weight_kg,
            province=str(province) if province is not None else None,
            city=str(city) if city is not None else None,
            district=str(district) if district is not None else None,
            provider_ids=None,
        )

        quotes_raw = raw.get("quotes") or []
        quotes: list[ShipPrepareQuoteCandidateOut] = []
        for q in quotes_raw:
            quotes.append(
                ShipPrepareQuoteCandidateOut(
                    provider_id=int(q["provider_id"]),
                    shipping_provider_code=q.get("shipping_provider_code"),
                    shipping_provider_name=str(q.get("shipping_provider_name") or ""),
                    template_id=int(q["template_id"]),
                    template_name=q.get("template_name"),
                    quote_status=str(q.get("quote_status") or ""),
                    currency=q.get("currency"),
                    est_cost=float(q["total_amount"]) if q.get("total_amount") is not None else None,
                    reasons=list(q.get("reasons") or []),
                    breakdown=q.get("breakdown"),
                    eta=None,
                )
            )

        return ShipPreparePackageQuoteOut(
            package_no=int(package.package_no),
            warehouse_id=warehouse_id,
            weight_kg=weight_kg,
            province=str(province) if province is not None else None,
            city=str(city) if city is not None else None,
            district=str(district) if district is not None else None,
            quotes=quotes,
        )

    async def confirm_prepare_package_quote(
        self,
        *,
        platform: str,
        shop_id: str,
        ext_order_no: str,
        package_no: int,
        provider_id: int,
    ) -> ShipPreparePackageQuoteConfirmOut:
        _, _, package, address = await self._load_prepare_and_package_and_address(
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            package_no=package_no,
        )

        warehouse_id = int(package.warehouse_id)
        weight_kg = float(package.weight_kg)
        province = str(address.get("province")) if address.get("province") is not None else None
        city = str(address.get("city")) if address.get("city") is not None else None
        district = str(address.get("district")) if address.get("district") is not None else None

        raw = await self._recommend_package_quotes(
            warehouse_id=warehouse_id,
            weight_kg=weight_kg,
            province=province,
            city=city,
            district=district,
            provider_ids=[int(provider_id)],
        )
        quotes_raw = raw.get("quotes") or []

        selected_quote = None
        for q in quotes_raw:
            if int(q["provider_id"]) == int(provider_id):
                selected_quote = q
                break

        if selected_quote is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="selected provider quote not available for this package",
            )

        snapshot = build_quote_snapshot(
            source="shipping_quote.calc",
            input_payload={
                "warehouse_id": warehouse_id,
                "provider_id": int(selected_quote["provider_id"]),
            },
            selected_quote={
                "quote_status": str(selected_quote.get("quote_status") or ""),
                "template_id": int(selected_quote["template_id"]),
                "template_name": selected_quote.get("template_name"),
                "provider_id": int(selected_quote["provider_id"]),
                "shipping_provider_code": selected_quote.get("shipping_provider_code"),
                "shipping_provider_name": str(selected_quote.get("shipping_provider_name") or ""),
                "currency": selected_quote.get("currency"),
                "total_amount": float(selected_quote["total_amount"]),
                "weight": selected_quote.get("weight"),
                "destination_group": selected_quote.get("destination_group"),
                "pricing_matrix": selected_quote.get("pricing_matrix"),
                "breakdown": selected_quote.get("breakdown"),
                "reasons": list(selected_quote.get("reasons") or []),
            },
        )

        package.pricing_status = "calculated"
        package.selected_provider_id = int(provider_id)
        package.selected_quote_snapshot = snapshot

        await self.session.flush()
        await self.session.commit()

        return ShipPreparePackageQuoteConfirmOut(
            package_no=int(package.package_no),
            pricing_status=str(package.pricing_status),
            selected_provider_id=int(package.selected_provider_id),
            selected_quote_snapshot=snapshot,
        )
