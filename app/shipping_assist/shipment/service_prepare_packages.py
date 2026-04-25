# app/shipping_assist/shipment/service_prepare_packages.py
# 分拆说明：
# - 本文件从 service.py 中拆出“发运准备-包裹”相关能力。
# - 当前只负责：
#   1) 包裹列表读取
#   2) 新增包裹
#   3) 更新包裹基础信息（重量 / 发货仓）
# - 维护约束：
#   - 更新重量或发货仓时，必须清空旧报价事实：
#       pricing_status -> pending
#       selected_provider_id -> NULL
#       selected_quote_snapshot -> NULL
#   - 本文件不负责地址核对
#   - 本文件不负责报价确认
#   - 本文件不负责 ship_with_waybill 执行
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shipping_assist.shipment.models.order_shipment_prepare_package import OrderShipmentPreparePackage

from .contracts_prepare_packages import ShipPreparePackageOut


class ShipmentPreparePackagesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _load_order_row(
        self,
        *,
        platform: str,
        shop_id: str,
        ext_order_no: str,
    ) -> dict[str, object]:
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

    @staticmethod
    def _package_to_out(package: OrderShipmentPreparePackage) -> ShipPreparePackageOut:
        return ShipPreparePackageOut(
            package_no=int(package.package_no),
            weight_kg=float(package.weight_kg) if package.weight_kg is not None else None,
            warehouse_id=int(package.warehouse_id) if package.warehouse_id is not None else None,
            pricing_status=str(package.pricing_status or "pending"),
            selected_provider_id=(
                int(package.selected_provider_id)
                if package.selected_provider_id is not None
                else None
            ),
        )

    async def list_prepare_packages(
        self,
        *,
        platform: str,
        shop_id: str,
        ext_order_no: str,
    ) -> list[ShipPreparePackageOut]:
        order_row = await self._load_order_row(
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )
        order_id = int(order_row["id"])

        rows = (
            await self.session.execute(
                select(OrderShipmentPreparePackage)
                .where(OrderShipmentPreparePackage.order_id == order_id)
                .order_by(OrderShipmentPreparePackage.package_no.asc())
            )
        ).scalars().all()

        return [self._package_to_out(row) for row in rows]

    async def create_prepare_package(
        self,
        *,
        platform: str,
        shop_id: str,
        ext_order_no: str,
    ) -> ShipPreparePackageOut:
        order_row = await self._load_order_row(
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )
        order_id = int(order_row["id"])

        max_package_no = (
            await self.session.execute(
                text(
                    """
                    SELECT COALESCE(MAX(package_no), 0) AS max_package_no
                    FROM order_shipment_prepare_packages
                    WHERE order_id = :order_id
                    """
                ),
                {"order_id": order_id},
            )
        ).scalar_one()

        next_package_no = int(max_package_no) + 1

        package = OrderShipmentPreparePackage(
            order_id=order_id,
            package_no=next_package_no,
            weight_kg=None,
            warehouse_id=None,
            pricing_status="pending",
            selected_provider_id=None,
            selected_quote_snapshot=None,
        )
        self.session.add(package)
        await self.session.flush()
        await self.session.commit()

        return self._package_to_out(package)

    async def update_prepare_package(
        self,
        *,
        platform: str,
        shop_id: str,
        ext_order_no: str,
        package_no: int,
        weight_kg: float | None,
        warehouse_id: int | None,
    ) -> ShipPreparePackageOut:
        order_row = await self._load_order_row(
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )
        order_id = int(order_row["id"])

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

        if weight_kg is not None:
            package.weight_kg = weight_kg

        if warehouse_id is not None:
            package.warehouse_id = warehouse_id

        package.pricing_status = "pending"
        package.selected_provider_id = None
        package.selected_quote_snapshot = None

        await self.session.flush()
        await self.session.commit()

        return self._package_to_out(package)
