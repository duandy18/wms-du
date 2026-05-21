# tests/ci/test_wms_pms_read_projection_boundary.py
from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base, init_models

ROOT = Path(__file__).resolve().parents[2]

PROJECTION_COLUMNS: dict[str, set[str]] = {
    "wms_pms_supplier_projection": {
        "supplier_id",
        "supplier_code",
        "supplier_name",
        "active",
        "website",
        "pms_updated_at",
        "source_hash",
        "sync_version",
        "synced_at",
    },
    "wms_pms_item_projection": {
        "item_id",
        "sku",
        "name",
        "spec",
        "enabled",
        "supplier_id",
        "brand",
        "category",
        "expiry_policy",
        "shelf_life_value",
        "shelf_life_unit",
        "lot_source_policy",
        "derivation_allowed",
        "uom_governance_enabled",
        "pms_updated_at",
        "source_hash",
        "sync_version",
        "synced_at",
    },
    "wms_pms_uom_projection": {
        "item_uom_id",
        "item_id",
        "uom",
        "display_name",
        "uom_name",
        "ratio_to_base",
        "net_weight_kg",
        "is_base",
        "is_purchase_default",
        "is_inbound_default",
        "is_outbound_default",
        "pms_updated_at",
        "source_hash",
        "sync_version",
        "synced_at",
    },
    "wms_pms_sku_code_projection": {
        "sku_code_id",
        "item_id",
        "sku_code",
        "code_type",
        "is_primary",
        "is_active",
        "effective_from",
        "effective_to",
        "pms_updated_at",
        "source_hash",
        "sync_version",
        "synced_at",
    },
    "wms_pms_barcode_projection": {
        "barcode_id",
        "item_id",
        "item_uom_id",
        "barcode",
        "symbology",
        "active",
        "is_primary",
        "pms_updated_at",
        "source_hash",
        "sync_version",
        "synced_at",
    },
}

BUSINESS_DIRS = (
    "app/wms",
    "app/oms",
    "app/procurement",
    "app/finance",
)

BUSINESS_PROJECTION_WRITE_RE = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+wms_pms_",
    re.IGNORECASE,
)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def test_db_base_loads_wms_pms_projection_models() -> None:
    text_value = (ROOT / "app" / "db" / "base.py").read_text(encoding="utf-8")

    assert '"app.integrations.pms.projection_models"' in text_value


def test_wms_pms_projection_tables_are_registered_in_metadata() -> None:
    init_models(force=True)

    for table_name, expected_columns in PROJECTION_COLUMNS.items():
        assert table_name in Base.metadata.tables

        table = Base.metadata.tables[table_name]
        assert table.info["owner"] == "wms-api"
        assert table.info["source_owner"] == "pms-api"
        assert table.info["projection"] is True
        assert table.info["read_only_index"] is True
        assert set(table.c.keys()) == expected_columns


def test_wms_pms_projection_tables_do_not_point_to_pms_owner_tables() -> None:
    init_models(force=True)

    for table_name in PROJECTION_COLUMNS:
        table = Base.metadata.tables[table_name]
        assert list(table.foreign_keys) == []


def test_wms_pms_projection_data_tables_have_no_relationships_or_foreign_keys() -> None:
    init_models(force=True)

    for table_name in PROJECTION_COLUMNS:
        table = Base.metadata.tables[table_name]
        assert list(table.foreign_keys) == []

    text_value = (ROOT / "app/integrations/pms/projection_models.py").read_text(encoding="utf-8")
    assert "relationship(" not in text_value


def test_wms_pms_projection_contracts_do_not_import_owner_or_db_runtime() -> None:
    text_value = (ROOT / "app/integrations/pms/projection_contracts.py").read_text(encoding="utf-8")

    assert "app.pms" not in text_value
    assert "sqlalchemy" not in text_value


def test_business_domains_do_not_write_wms_pms_projection_tables() -> None:
    violations: list[str] = []

    for directory in BUSINESS_DIRS:
        root = ROOT / directory
        if not root.exists():
            continue

        for path in sorted(root.rglob("*.py")):
            rel = _rel(path)
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if BUSINESS_PROJECTION_WRITE_RE.search(line):
                    violations.append(f"{rel}:{line_no}: {line.strip()}")

    assert violations == []


@pytest.mark.asyncio
async def test_wms_pms_projection_primary_keys_have_no_db_defaults(
    session: AsyncSession,
) -> None:
    rows = await session.execute(
        text(
            """
            SELECT table_name, column_name, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND (table_name, column_name) IN (
                ('wms_pms_supplier_projection', 'supplier_id'),
                ('wms_pms_item_projection', 'item_id'),
                ('wms_pms_uom_projection', 'item_uom_id'),
                ('wms_pms_sku_code_projection', 'sku_code_id'),
                ('wms_pms_barcode_projection', 'barcode_id')
              )
            ORDER BY table_name, column_name
            """
        )
    )

    got = {
        (str(row["table_name"]), str(row["column_name"])): row["column_default"]
        for row in rows.mappings().all()
    }

    assert got == {
        ("wms_pms_barcode_projection", "barcode_id"): None,
        ("wms_pms_item_projection", "item_id"): None,
        ("wms_pms_supplier_projection", "supplier_id"): None,
        ("wms_pms_sku_code_projection", "sku_code_id"): None,
        ("wms_pms_uom_projection", "item_uom_id"): None,
    }
