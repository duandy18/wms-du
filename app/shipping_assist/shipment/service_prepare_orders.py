# app/shipping_assist/shipment/service_prepare_orders.py
# 分拆说明：
# - 本文件从 service.py 中拆出“发运准备-订单与地址”相关能力。
# - 当前只负责：
#   1) 导入订单到发运准备池
#   2) 发运准备列表读取
#   3) 单订单基础详情读取
#   4) 地址核对写入
# - 维护约束：
#   - 本文件不负责包裹创建/更新
#   - 本文件不负责报价确认
#   - 本文件不负责 ship_with_waybill 执行
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shipping_assist.shipment.models.order_shipment_prepare import OrderShipmentPrepare

from .contracts_prepare_orders import (
    ShipPrepareImportResponse,
    ShipPrepareOrderDetailOut,
    ShipPrepareOrdersListItemOut,
)


class ShipmentPrepareOrdersService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _clean_text(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _normalize_address_ready_status(value: str | None) -> str:
        raw = (value or "").strip().lower()
        if raw not in {"pending", "ready"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="address_ready_status must be one of: pending, ready",
            )
        return raw

    @staticmethod
    def _normalize_address_confirm_status(value: str | None) -> str:
        raw = (value or "").strip().lower()
        if raw != "ready":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="address_confirm currently only supports ready",
            )
        return raw

    @staticmethod
    def _build_address_summary(
        *,
        province: str | None,
        city: str | None,
        district: str | None,
        detail: str | None,
    ) -> str:
        parts = [
            (province or "").strip(),
            (city or "").strip(),
            (district or "").strip(),
            (detail or "").strip(),
        ]
        filtered = [x for x in parts if x]
        return " ".join(filtered) if filtered else "-"

    async def _load_order_row(
        self,
        *,
        platform: str,
        store_code: str,
        ext_order_no: str,
    ) -> dict[str, object]:
        plat = (platform or "").strip().upper()
        sid = (store_code or "").strip()
        ext = (ext_order_no or "").strip()

        if not plat or not sid or not ext:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="platform / store_code / ext_order_no are required",
            )

        row = (
            await self.session.execute(
                text(
                    """
                    SELECT id, platform, store_code, ext_order_no
                    FROM orders
                    WHERE platform = :platform
                      AND store_code = :store_code
                      AND ext_order_no = :ext_order_no
                    LIMIT 1
                    """
                ),
                {
                    "platform": plat,
                    "store_code": sid,
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

    async def import_order_to_prepare(
        self,
        *,
        platform: str,
        store_code: str,
        ext_order_no: str,
        address_ready_status: str,
    ) -> ShipPrepareImportResponse:
        plat = (platform or "").strip().upper()
        sid = (store_code or "").strip()
        ext = (ext_order_no or "").strip()
        addr_status = self._normalize_address_ready_status(address_ready_status)

        if not plat or not sid or not ext:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="platform / store_code / ext_order_no are required",
            )

        order_sql = text(
            """
            SELECT id, platform, store_code, ext_order_no
            FROM orders
            WHERE platform = :platform
              AND store_code = :store_code
              AND ext_order_no = :ext_order_no
            LIMIT 1
            """
        )
        row = (
            await self.session.execute(
                order_sql,
                {"platform": plat, "store_code": sid, "ext_order_no": ext},
            )
        ).mappings().first()

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="order not found",
            )

        order_id = int(row["id"])
        prepare = await self.session.scalar(
            select(OrderShipmentPrepare).where(OrderShipmentPrepare.order_id == order_id)
        )

        if prepare is None:
            prepare = OrderShipmentPrepare(
                order_id=order_id,
                address_ready_status=addr_status,
                package_status="pending",
                pricing_status="pending",
                provider_status="pending",
            )
            self.session.add(prepare)
        else:
            prepare.address_ready_status = addr_status

        await self.session.flush()
        await self.session.commit()

        return ShipPrepareImportResponse(
            ok=True,
            order_id=order_id,
            platform=plat,
            store_code=sid,
            ext_order_no=ext,
            address_ready_status=addr_status,
        )

    async def list_prepare_orders(self, *, limit: int) -> list[ShipPrepareOrdersListItemOut]:
        list_sql = text(
            """
            SELECT
                o.id AS order_id,
                o.platform,
                o.store_code,
                o.ext_order_no,
                a.receiver_name,
                a.receiver_phone,
                a.province,
                a.city,
                a.district,
                a.detail
            FROM order_shipment_prepare p
            JOIN orders o
              ON o.id = p.order_id
            LEFT JOIN order_address a
              ON a.order_id = o.id
            ORDER BY o.id DESC
            LIMIT :limit
            """
        )

        rows = (
            await self.session.execute(list_sql, {"limit": int(limit)})
        ).mappings().all()

        out: list[ShipPrepareOrdersListItemOut] = []
        for row in rows:
            province = self._clean_text(row.get("province"))
            city = self._clean_text(row.get("city"))
            district = self._clean_text(row.get("district"))
            detail = self._clean_text(row.get("detail"))

            out.append(
                ShipPrepareOrdersListItemOut(
                    order_id=int(row["order_id"]),
                    platform=str(row["platform"]),
                    store_code=str(row["store_code"]),
                    ext_order_no=str(row["ext_order_no"]),
                    receiver_name=self._clean_text(row.get("receiver_name")),
                    receiver_phone=self._clean_text(row.get("receiver_phone")),
                    province=province,
                    city=city,
                    district=district,
                    detail=detail,
                    address_summary=self._build_address_summary(
                        province=province,
                        city=city,
                        district=district,
                        detail=detail,
                    ),
                )
            )

        return out

    async def get_prepare_order_detail(
        self,
        *,
        platform: str,
        store_code: str,
        ext_order_no: str,
    ) -> ShipPrepareOrderDetailOut:
        plat = (platform or "").strip().upper()
        sid = (store_code or "").strip()
        ext = (ext_order_no or "").strip()

        if not plat or not sid or not ext:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="platform / store_code / ext_order_no are required",
            )

        detail_sql = text(
            """
            SELECT
                o.id AS order_id,
                o.platform,
                o.store_code,
                o.ext_order_no,
                a.receiver_name,
                a.receiver_phone,
                a.province,
                a.city,
                a.district,
                a.detail,
                p.address_ready_status
            FROM orders o
            LEFT JOIN order_address a
              ON a.order_id = o.id
            LEFT JOIN order_shipment_prepare p
              ON p.order_id = o.id
            WHERE o.platform = :platform
              AND o.store_code = :store_code
              AND o.ext_order_no = :ext_order_no
            LIMIT 1
            """
        )

        row = (
            await self.session.execute(
                detail_sql,
                {
                    "platform": plat,
                    "store_code": sid,
                    "ext_order_no": ext,
                },
            )
        ).mappings().first()

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="order not found",
            )

        province = self._clean_text(row.get("province"))
        city = self._clean_text(row.get("city"))
        district = self._clean_text(row.get("district"))
        detail = self._clean_text(row.get("detail"))
        address_ready_status = self._normalize_address_ready_status(
            row.get("address_ready_status") or "pending"
        )

        return ShipPrepareOrderDetailOut(
            order_id=int(row["order_id"]),
            platform=str(row["platform"]),
            store_code=str(row["store_code"]),
            ext_order_no=str(row["ext_order_no"]),
            receiver_name=self._clean_text(row.get("receiver_name")),
            receiver_phone=self._clean_text(row.get("receiver_phone")),
            province=province,
            city=city,
            district=district,
            detail=detail,
            address_summary=self._build_address_summary(
                province=province,
                city=city,
                district=district,
                detail=detail,
            ),
            address_ready_status=address_ready_status,
        )

    async def confirm_order_address_ready(
        self,
        *,
        platform: str,
        store_code: str,
        ext_order_no: str,
        address_ready_status: str,
    ) -> ShipPrepareOrderDetailOut:
        plat = (platform or "").strip().upper()
        sid = (store_code or "").strip()
        ext = (ext_order_no or "").strip()
        ready_status = self._normalize_address_confirm_status(address_ready_status)

        if not plat or not sid or not ext:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="platform / store_code / ext_order_no are required",
            )

        order_sql = text(
            """
            SELECT id
            FROM orders
            WHERE platform = :platform
              AND store_code = :store_code
              AND ext_order_no = :ext_order_no
            LIMIT 1
            """
        )
        row = (
            await self.session.execute(
                order_sql,
                {
                    "platform": plat,
                    "store_code": sid,
                    "ext_order_no": ext,
                },
            )
        ).mappings().first()

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="order not found",
            )

        order_id = int(row["id"])
        prepare = await self.session.scalar(
            select(OrderShipmentPrepare).where(OrderShipmentPrepare.order_id == order_id)
        )

        if prepare is None:
            prepare = OrderShipmentPrepare(
                order_id=order_id,
                address_ready_status=ready_status,
                package_status="pending",
                pricing_status="pending",
                provider_status="pending",
            )
            self.session.add(prepare)
        else:
            prepare.address_ready_status = ready_status

        await self.session.flush()
        await self.session.commit()

        return await self.get_prepare_order_detail(
            platform=plat,
            store_code=sid,
            ext_order_no=ext,
        )
