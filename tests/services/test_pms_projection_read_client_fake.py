# tests/services/test_pms_projection_read_client_fake.py
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.pms_projection import seed_pms_projection_item_with_base_uom
from tests.helpers.pms_read_client_fake import ProjectionBackedFakePmsReadClient


@pytest.mark.asyncio
async def test_projection_backed_fake_pms_read_client_reads_item_policy_and_basic(
    session: AsyncSession,
) -> None:
    await seed_pms_projection_item_with_base_uom(
        session,
        item_id=992001,
        item_uom_id=992011,
        sku_code_id=992021,
        sku="UT-PMS-FAKE-992001",
        name="UT PMS Fake Item 992001",
        expiry_policy="REQUIRED",
    )
    await session.commit()

    client = ProjectionBackedFakePmsReadClient(session)

    basic = await client.get_item_basic(item_id=992001)
    assert basic is not None
    assert basic.id == 992001
    assert basic.sku == "UT-PMS-FAKE-992001"
    assert basic.name == "UT PMS Fake Item 992001"

    policy = await client.get_item_policy(item_id=992001)
    assert policy is not None
    assert policy.item_id == 992001
    assert policy.expiry_policy == "REQUIRED"
    assert policy.lot_source_policy == "SUPPLIER_ONLY"
    assert policy.shelf_life_value == 30
    assert policy.shelf_life_unit == "DAY"

    by_sku = await client.get_item_policy_by_sku(sku="UT-PMS-FAKE-992001")
    assert by_sku is not None
    assert by_sku.item_id == 992001
    assert by_sku.expiry_policy == "REQUIRED"


@pytest.mark.asyncio
async def test_projection_backed_fake_pms_read_client_reads_uoms(
    session: AsyncSession,
) -> None:
    await seed_pms_projection_item_with_base_uom(
        session,
        item_id=992002,
        item_uom_id=992012,
        sku_code_id=992022,
        sku="UT-PMS-FAKE-992002",
        name="UT PMS Fake Item 992002",
        expiry_policy="NONE",
    )
    await session.commit()

    client = ProjectionBackedFakePmsReadClient(session)

    by_id = await client.get_uom(item_uom_id=992012)
    assert by_id is not None
    assert by_id.id == 992012
    assert by_id.item_id == 992002
    assert by_id.uom == "PCS"
    assert by_id.ratio_to_base == 1

    by_item = await client.list_uoms_by_item_id(item_id=992002)
    assert len(by_item) == 1
    assert by_item[0].id == 992012

    inbound_default = await client.get_inbound_default_or_base_uom(item_id=992002)
    assert inbound_default is not None
    assert inbound_default.id == 992012

    outbound_default = await client.get_outbound_default_or_base_uom(item_id=992002)
    assert outbound_default is not None
    assert outbound_default.id == 992012

@pytest.mark.asyncio
async def test_projection_backed_fake_pms_read_client_reads_report_meta(
    session: AsyncSession,
) -> None:
    await seed_pms_projection_item_with_base_uom(
        session,
        item_id=992003,
        item_uom_id=992013,
        sku_code_id=992023,
        sku="UT-PMS-FAKE-992003",
        name="UT PMS Fake Item 992003",
        expiry_policy="NONE",
    )
    await session.commit()

    client = ProjectionBackedFakePmsReadClient(session)

    meta = await client.get_report_meta_by_item_ids(item_ids=[992003])
    assert sorted(meta) == [992003]
    assert meta[992003].sku == "UT-PMS-FAKE-992003"
    assert meta[992003].name == "UT PMS Fake Item 992003"

    matched_ids = await client.search_report_item_ids_by_keyword(keyword="992003")
    assert matched_ids == [992003]
