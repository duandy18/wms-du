# tests/services/test_shipment_prepare_service.py
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.tms.shipment.service_prepare_orders import ShipmentPrepareOrdersService
from tests.services.pick._seed_orders import insert_min_order
from tests.utils.ensure_minimal import ensure_warehouse

pytestmark = pytest.mark.asyncio


async def _seed_prepare_order_case(
    session: AsyncSession,
    *,
    address_ready_status: str | None = None,
) -> dict[str, object]:
    uniq = uuid4().hex[:10]
    platform = "PDD"
    shop_id = "1"
    ext_order_no = f"PREPARE-UT-{uniq}"
    trace_id = f"TRACE-{uniq}"
    warehouse_id = 1

    await ensure_warehouse(session, id=warehouse_id, name=f"WH-{warehouse_id}")

    order_id = await insert_min_order(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        warehouse_id=warehouse_id,
        fulfillment_status="SERVICE_ASSIGNED",
        status="CREATED",
        trace_id=trace_id,
    )

    await session.execute(
        text(
            """
            INSERT INTO order_address (
                order_id,
                receiver_name,
                receiver_phone,
                province,
                city,
                district,
                detail
            )
            VALUES (
                :order_id,
                '张三',
                '13800000000',
                '北京市',
                '北京市',
                '朝阳区',
                '测试地址 1 号'
            )
            ON CONFLICT (order_id) DO UPDATE
               SET receiver_name = EXCLUDED.receiver_name,
                   receiver_phone = EXCLUDED.receiver_phone,
                   province = EXCLUDED.province,
                   city = EXCLUDED.city,
                   district = EXCLUDED.district,
                   detail = EXCLUDED.detail
            """
        ),
        {"order_id": int(order_id)},
    )

    if address_ready_status is not None:
        await session.execute(
            text(
                """
                INSERT INTO order_shipment_prepare (
                    order_id,
                    address_ready_status,
                    package_status,
                    pricing_status,
                    provider_status
                )
                VALUES (
                    :order_id,
                    :address_ready_status,
                    'pending',
                    'pending',
                    'pending'
                )
                ON CONFLICT (order_id) DO UPDATE
                   SET address_ready_status = EXCLUDED.address_ready_status,
                       package_status = EXCLUDED.package_status,
                       pricing_status = EXCLUDED.pricing_status,
                       provider_status = EXCLUDED.provider_status
                """
            ),
            {
                "order_id": int(order_id),
                "address_ready_status": str(address_ready_status),
            },
        )

    await session.commit()

    return {
        "order_id": int(order_id),
        "platform": platform,
        "shop_id": shop_id,
        "ext_order_no": ext_order_no,
    }


async def test_get_prepare_order_detail_returns_pending_when_prepare_missing(
    session: AsyncSession,
) -> None:
    svc = ShipmentPrepareOrdersService(session)
    ctx = await _seed_prepare_order_case(session, address_ready_status=None)

    detail = await svc.get_prepare_order_detail(
        platform=str(ctx["platform"]),
        shop_id=str(ctx["shop_id"]),
        ext_order_no=str(ctx["ext_order_no"]),
    )

    assert detail.order_id == int(ctx["order_id"])
    assert detail.platform == str(ctx["platform"])
    assert detail.shop_id == str(ctx["shop_id"])
    assert detail.ext_order_no == str(ctx["ext_order_no"])
    assert detail.receiver_name == "张三"
    assert detail.receiver_phone == "13800000000"
    assert detail.province == "北京市"
    assert detail.city == "北京市"
    assert detail.district == "朝阳区"
    assert detail.detail == "测试地址 1 号"
    assert detail.address_summary == "北京市 北京市 朝阳区 测试地址 1 号"
    assert detail.address_ready_status == "pending"


async def test_get_prepare_order_detail_returns_existing_ready_status(
    session: AsyncSession,
) -> None:
    svc = ShipmentPrepareOrdersService(session)
    ctx = await _seed_prepare_order_case(session, address_ready_status="ready")

    detail = await svc.get_prepare_order_detail(
        platform=str(ctx["platform"]),
        shop_id=str(ctx["shop_id"]),
        ext_order_no=str(ctx["ext_order_no"]),
    )

    assert detail.order_id == int(ctx["order_id"])
    assert detail.address_ready_status == "ready"


async def test_confirm_order_address_ready_creates_prepare_row_when_missing(
    session: AsyncSession,
) -> None:
    svc = ShipmentPrepareOrdersService(session)
    ctx = await _seed_prepare_order_case(session, address_ready_status=None)

    detail = await svc.confirm_order_address_ready(
        platform=str(ctx["platform"]),
        shop_id=str(ctx["shop_id"]),
        ext_order_no=str(ctx["ext_order_no"]),
        address_ready_status="ready",
    )

    assert detail.order_id == int(ctx["order_id"])
    assert detail.address_ready_status == "ready"

    row = (
        await session.execute(
            text(
                """
                SELECT
                  address_ready_status,
                  package_status,
                  pricing_status,
                  provider_status
                FROM order_shipment_prepare
                WHERE order_id = :order_id
                LIMIT 1
                """
            ),
            {"order_id": int(ctx["order_id"])},
        )
    ).mappings().first()

    assert row is not None
    assert row["address_ready_status"] == "ready"
    assert row["package_status"] == "pending"
    assert row["pricing_status"] == "pending"
    assert row["provider_status"] == "pending"


async def test_confirm_order_address_ready_updates_existing_prepare_row(
    session: AsyncSession,
) -> None:
    svc = ShipmentPrepareOrdersService(session)
    ctx = await _seed_prepare_order_case(session, address_ready_status="pending")

    detail = await svc.confirm_order_address_ready(
        platform=str(ctx["platform"]),
        shop_id=str(ctx["shop_id"]),
        ext_order_no=str(ctx["ext_order_no"]),
        address_ready_status="ready",
    )

    assert detail.order_id == int(ctx["order_id"])
    assert detail.address_ready_status == "ready"

    row = (
        await session.execute(
            text(
                """
                SELECT address_ready_status
                FROM order_shipment_prepare
                WHERE order_id = :order_id
                LIMIT 1
                """
            ),
            {"order_id": int(ctx["order_id"])},
        )
    ).mappings().first()

    assert row is not None
    assert row["address_ready_status"] == "ready"
