# tests/services/test_shipment_prepare_packages.py
from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.tms.shipment.service_prepare_packages import ShipmentPreparePackagesService
from tests.services.pick._seed_orders import insert_min_order
from tests.utils.ensure_minimal import ensure_warehouse

pytestmark = pytest.mark.asyncio


async def _seed_order_only(session: AsyncSession) -> dict[str, object]:
    uniq = uuid4().hex[:10]
    platform = "PDD"
    shop_id = "1"
    ext_order_no = f"PREPARE-PKG-{uniq}"
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
    await session.commit()

    return {
        "order_id": int(order_id),
        "platform": platform,
        "shop_id": shop_id,
        "ext_order_no": ext_order_no,
    }


async def _insert_package(
    session: AsyncSession,
    *,
    order_id: int,
    package_no: int,
    weight_kg: float | None = None,
    warehouse_id: int | None = None,
    pricing_status: str = "pending",
    selected_provider_id: int | None = None,
    selected_quote_snapshot: dict[str, object] | None = None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO order_shipment_prepare_packages (
                order_id,
                package_no,
                weight_kg,
                warehouse_id,
                pricing_status,
                selected_provider_id,
                selected_quote_snapshot,
                created_at,
                updated_at
            )
            VALUES (
                :order_id,
                :package_no,
                :weight_kg,
                :warehouse_id,
                :pricing_status,
                :selected_provider_id,
                CAST(:selected_quote_snapshot AS jsonb),
                now(),
                now()
            )
            ON CONFLICT (order_id, package_no) DO UPDATE
               SET weight_kg = EXCLUDED.weight_kg,
                   warehouse_id = EXCLUDED.warehouse_id,
                   pricing_status = EXCLUDED.pricing_status,
                   selected_provider_id = EXCLUDED.selected_provider_id,
                   selected_quote_snapshot = EXCLUDED.selected_quote_snapshot,
                   updated_at = now()
            """
        ),
        {
            "order_id": int(order_id),
            "package_no": int(package_no),
            "weight_kg": weight_kg,
            "warehouse_id": warehouse_id,
            "pricing_status": str(pricing_status),
            "selected_provider_id": selected_provider_id,
            "selected_quote_snapshot": (
                json.dumps(selected_quote_snapshot, ensure_ascii=False)
                if selected_quote_snapshot is not None
                else None
            ),
        },
    )


async def test_create_prepare_package_increments_package_no(
    session: AsyncSession,
) -> None:
    svc = ShipmentPreparePackagesService(session)
    ctx = await _seed_order_only(session)

    item1 = await svc.create_prepare_package(
        platform=str(ctx["platform"]),
        shop_id=str(ctx["shop_id"]),
        ext_order_no=str(ctx["ext_order_no"]),
    )
    item2 = await svc.create_prepare_package(
        platform=str(ctx["platform"]),
        shop_id=str(ctx["shop_id"]),
        ext_order_no=str(ctx["ext_order_no"]),
    )

    assert item1.package_no == 1
    assert item2.package_no == 2
    assert item1.pricing_status == "pending"
    assert item2.pricing_status == "pending"


async def test_list_prepare_packages_returns_ordered_rows(
    session: AsyncSession,
) -> None:
    svc = ShipmentPreparePackagesService(session)
    ctx = await _seed_order_only(session)

    await _insert_package(session, order_id=int(ctx["order_id"]), package_no=2, weight_kg=2.5)
    await _insert_package(session, order_id=int(ctx["order_id"]), package_no=1, weight_kg=1.2)
    await session.commit()

    items = await svc.list_prepare_packages(
        platform=str(ctx["platform"]),
        shop_id=str(ctx["shop_id"]),
        ext_order_no=str(ctx["ext_order_no"]),
    )

    assert [item.package_no for item in items] == [1, 2]
    assert items[0].weight_kg == pytest.approx(1.2)
    assert items[1].weight_kg == pytest.approx(2.5)


async def test_update_prepare_package_writes_weight_and_warehouse(
    session: AsyncSession,
) -> None:
    svc = ShipmentPreparePackagesService(session)
    ctx = await _seed_order_only(session)

    await _insert_package(
        session,
        order_id=int(ctx["order_id"]),
        package_no=1,
        weight_kg=None,
        warehouse_id=None,
        pricing_status="pending",
    )
    await session.commit()

    item = await svc.update_prepare_package(
        platform=str(ctx["platform"]),
        shop_id=str(ctx["shop_id"]),
        ext_order_no=str(ctx["ext_order_no"]),
        package_no=1,
        weight_kg=3.21,
        warehouse_id=1,
    )

    assert item.package_no == 1
    assert item.weight_kg == pytest.approx(3.21)
    assert item.warehouse_id == 1
    assert item.pricing_status == "pending"
    assert item.selected_provider_id is None


async def test_update_prepare_package_resets_quote_related_fields(
    session: AsyncSession,
) -> None:
    svc = ShipmentPreparePackagesService(session)
    ctx = await _seed_order_only(session)

    await _insert_package(
        session,
        order_id=int(ctx["order_id"]),
        package_no=1,
        weight_kg=1.11,
        warehouse_id=1,
        pricing_status="calculated",
        selected_provider_id=1,
        selected_quote_snapshot={"selected_quote": {"provider_id": 1}},
    )
    await session.commit()

    item = await svc.update_prepare_package(
        platform=str(ctx["platform"]),
        shop_id=str(ctx["shop_id"]),
        ext_order_no=str(ctx["ext_order_no"]),
        package_no=1,
        weight_kg=2.22,
        warehouse_id=1,
    )

    assert item.package_no == 1
    assert item.weight_kg == pytest.approx(2.22)
    assert item.pricing_status == "pending"
    assert item.selected_provider_id is None

    row = (
        await session.execute(
            text(
                """
                SELECT
                  pricing_status,
                  selected_provider_id,
                  selected_quote_snapshot
                FROM order_shipment_prepare_packages
                WHERE order_id = :order_id
                  AND package_no = 1
                LIMIT 1
                """
            ),
            {"order_id": int(ctx["order_id"])},
        )
    ).mappings().first()

    assert row is not None
    assert row["pricing_status"] == "pending"
    assert row["selected_provider_id"] is None
    assert row["selected_quote_snapshot"] is None
