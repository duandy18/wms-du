# tests/services/test_shipment_prepare_quotes.py
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.tms.shipment.service_prepare_quotes import ShipmentPrepareQuotesService
from tests.services.pick._seed_orders import insert_min_order
from tests.utils.ensure_minimal import ensure_warehouse

pytestmark = pytest.mark.asyncio


async def _pick_existing_binding(
    session: AsyncSession,
) -> dict[str, int]:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  wsp.warehouse_id,
                  wsp.shipping_provider_id
                FROM warehouse_shipping_providers wsp
                JOIN shipping_providers sp
                  ON sp.id = wsp.shipping_provider_id
                WHERE COALESCE(wsp.active, TRUE) = TRUE
                  AND COALESCE(sp.active, TRUE) = TRUE
                  AND wsp.active_template_id IS NOT NULL
                ORDER BY wsp.warehouse_id ASC, wsp.shipping_provider_id ASC
                LIMIT 1
                """
            )
        )
    ).mappings().first()

    assert row is not None, "no active warehouse/provider/template binding found"
    return {
        "warehouse_id": int(row["warehouse_id"]),
        "provider_id": int(row["shipping_provider_id"]),
    }


async def _seed_prepare_quote_case(
    session: AsyncSession,
    *,
    address_ready_status: str = "ready",
    weight_kg: float | None = 1.25,
    with_warehouse: bool = True,
) -> dict[str, object]:
    uniq = uuid4().hex[:10]
    platform = "PDD"
    shop_id = "1"
    ext_order_no = f"QUOTE-UT-{uniq}"
    trace_id = f"TRACE-{uniq}"

    binding = await _pick_existing_binding(session)
    warehouse_id = int(binding["warehouse_id"])
    provider_id = int(binding["provider_id"])

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
            "address_ready_status": address_ready_status,
        },
    )

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
                1,
                :weight_kg,
                :warehouse_id,
                'pending',
                NULL,
                NULL,
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
            "weight_kg": weight_kg,
            "warehouse_id": warehouse_id if with_warehouse else None,
        },
    )

    await session.commit()

    return {
        "order_id": int(order_id),
        "platform": platform,
        "shop_id": shop_id,
        "ext_order_no": ext_order_no,
        "warehouse_id": warehouse_id,
        "provider_id": provider_id,
    }


async def test_quote_prepare_package_returns_candidates(
    session: AsyncSession,
) -> None:
    svc = ShipmentPrepareQuotesService(session)
    ctx = await _seed_prepare_quote_case(session)

    out = await svc.quote_prepare_package(
        platform=str(ctx["platform"]),
        shop_id=str(ctx["shop_id"]),
        ext_order_no=str(ctx["ext_order_no"]),
        package_no=1,
    )

    assert out.package_no == 1
    assert out.warehouse_id == int(ctx["warehouse_id"])
    assert out.weight_kg == pytest.approx(1.25)
    assert out.quotes, "expected non-empty quote candidates"
    assert any(int(q.provider_id) == int(ctx["provider_id"]) for q in out.quotes)


async def test_quote_prepare_package_rejects_when_address_not_ready(
    session: AsyncSession,
) -> None:
    svc = ShipmentPrepareQuotesService(session)
    ctx = await _seed_prepare_quote_case(session, address_ready_status="pending")

    with pytest.raises(Exception) as exc_info:
        await svc.quote_prepare_package(
            platform=str(ctx["platform"]),
            shop_id=str(ctx["shop_id"]),
            ext_order_no=str(ctx["ext_order_no"]),
            package_no=1,
        )

    assert "address_ready_status must be ready" in str(exc_info.value)


async def test_quote_prepare_package_rejects_when_weight_missing(
    session: AsyncSession,
) -> None:
    svc = ShipmentPrepareQuotesService(session)
    ctx = await _seed_prepare_quote_case(session, weight_kg=None)

    with pytest.raises(Exception) as exc_info:
        await svc.quote_prepare_package(
            platform=str(ctx["platform"]),
            shop_id=str(ctx["shop_id"]),
            ext_order_no=str(ctx["ext_order_no"]),
            package_no=1,
        )

    assert "weight_kg is required" in str(exc_info.value)


async def test_confirm_prepare_package_quote_writes_snapshot(
    session: AsyncSession,
) -> None:
    svc = ShipmentPrepareQuotesService(session)
    ctx = await _seed_prepare_quote_case(session)

    out = await svc.confirm_prepare_package_quote(
        platform=str(ctx["platform"]),
        shop_id=str(ctx["shop_id"]),
        ext_order_no=str(ctx["ext_order_no"]),
        package_no=1,
        provider_id=int(ctx["provider_id"]),
    )

    assert out.package_no == 1
    assert out.pricing_status == "calculated"
    assert out.selected_provider_id == int(ctx["provider_id"])
    assert isinstance(out.selected_quote_snapshot, dict)

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
    assert row["pricing_status"] == "calculated"
    assert int(row["selected_provider_id"]) == int(ctx["provider_id"])
    assert isinstance(row["selected_quote_snapshot"], dict)
