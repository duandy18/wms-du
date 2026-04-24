# tests/ci/test_pms_item_compat_contract.py
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.pms.items.contracts.item import ItemCreate, ItemOut, ItemUpdate
from app.pms.public.items.contracts.item_basic import ItemBasic


def test_pms_owner_item_contract_keeps_compat_output_but_forbids_write_inputs() -> None:
    """
    PMS owner /items 合同边界：

    - barcode / primary_barcode / weight_kg 仍是 owner 输出字段；
    - 它们是运行时投影/兼容输出，不是 items 表事实字段；
    - ItemCreate / ItemUpdate 不允许这些字段作为写入输入。
    """
    owner_output_fields = set(ItemOut.model_fields)
    assert {"barcode", "primary_barcode", "weight_kg"} <= owner_output_fields

    create_input_fields = set(ItemCreate.model_fields)
    update_input_fields = set(ItemUpdate.model_fields)

    forbidden_write_inputs = {"barcode", "primary_barcode", "weight_kg", "uom", "unit"}
    assert forbidden_write_inputs.isdisjoint(create_input_fields)
    assert forbidden_write_inputs.isdisjoint(update_input_fields)


def test_pms_public_item_basic_excludes_owner_compat_and_subtable_fields() -> None:
    """
    PMS public ItemBasic 是跨域最小读模型：

    - 不暴露 owner 兼容输出；
    - 不混入 item_barcodes / item_uoms 子表事实；
    - 需要条码/包装/净重时，调用 public aggregate 或 barcode probe。
    """
    fields = set(ItemBasic.model_fields)

    assert {"id", "sku", "name", "spec", "enabled", "supplier_id", "brand", "category"} <= fields

    forbidden_public_basic_fields = {
        "barcode",
        "primary_barcode",
        "weight_kg",
        "net_weight_kg",
        "uom",
        "unit",
        "item_uom_id",
        "base_item_uom_id",
    }
    assert forbidden_public_basic_fields.isdisjoint(fields)


@pytest.mark.asyncio
async def test_pms_item_compat_fields_are_not_reintroduced_on_items_table(
    session: AsyncSession,
) -> None:
    """
    DB schema 护栏：

    - items 表不得重新出现 barcode / primary_barcode / weight_kg / uom / unit；
    - 条码真相源必须是 item_barcodes；
    - 净重真相源必须是 item_uoms.net_weight_kg。
    """
    forbidden_rows = (
        await session.execute(
            text(
                """
                SELECT column_name
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name = 'items'
                   AND column_name IN (
                     'barcode',
                     'primary_barcode',
                     'weight_kg',
                     'net_weight_kg',
                     'uom',
                     'unit'
                   )
                 ORDER BY column_name
                """
            )
        )
    ).scalars().all()

    assert list(forbidden_rows) == []

    item_uom_columns = set(
        (
            await session.execute(
                text(
                    """
                    SELECT column_name
                      FROM information_schema.columns
                     WHERE table_schema = 'public'
                       AND table_name = 'item_uoms'
                    """
                )
            )
        ).scalars().all()
    )
    assert {"item_id", "uom", "ratio_to_base", "is_base", "net_weight_kg"} <= item_uom_columns

    item_barcode_columns = set(
        (
            await session.execute(
                text(
                    """
                    SELECT column_name
                      FROM information_schema.columns
                     WHERE table_schema = 'public'
                       AND table_name = 'item_barcodes'
                    """
                )
            )
        ).scalars().all()
    )
    assert {"item_id", "item_uom_id", "barcode", "is_primary", "active"} <= item_barcode_columns
