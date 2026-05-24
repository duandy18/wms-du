# tests/ci/test_wms_pms_projection_ops_boundary.py
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_OWNER_SQL_RE = re.compile(
    r"\bFROM\s+(items|item_uoms|item_sku_codes|item_barcodes|suppliers|supplier_contacts)\b"
    r"|\bJOIN\s+(items|item_uoms|item_sku_codes|item_barcodes|suppliers|supplier_contacts)\b"
    r"|\bINSERT\s+INTO\s+(items|item_uoms|item_sku_codes|item_barcodes|suppliers|supplier_contacts)\b"
    r"|\bUPDATE\s+(items|item_uoms|item_sku_codes|item_barcodes|suppliers|supplier_contacts)\b"
    r"|\bDELETE\s+FROM\s+(items|item_uoms|item_sku_codes|item_barcodes|suppliers|supplier_contacts)\b",
    re.IGNORECASE,
)


def test_pms_projection_module_uses_wms_directory_style() -> None:
    base = ROOT / "app/pms/projections"

    for relative in [
        "contracts/pms_projection.py",
        "contracts/items.py",
        "contracts/suppliers.py",
        "contracts/uoms.py",
        "contracts/sku_codes.py",
        "contracts/barcodes.py",
        "repos/pms_projection_repo.py",
        "services/pms_projection_service.py",
        "routers/pms_projection.py",
        "routers/deps.py",
        "routers/items.py",
        "routers/suppliers.py",
        "routers/uoms.py",
        "routers/sku_codes.py",
        "routers/barcodes.py",
    ]:
        assert (base / relative).is_file(), relative

    assert not (base / "contracts.py").exists()
    assert not (base / "service.py").exists()
    assert not (base / "router.py").exists()


def test_pms_projection_repo_uses_projection_tables_only() -> None:
    text = (ROOT / "app/pms/projections/repos/pms_projection_repo.py").read_text(encoding="utf-8")

    assert "wms_pms_item_projection" in text
    assert "wms_pms_supplier_projection" in text
    assert "wms_pms_uom_projection" in text
    assert "wms_pms_sku_code_projection" in text
    assert "wms_pms_barcode_projection" in text
    assert "wms_pms_projection_sync_runs" in text
    assert FORBIDDEN_OWNER_SQL_RE.search(text) is None


def test_pms_projection_service_is_not_sql_repo() -> None:
    text = (ROOT / "app/pms/projections/services/pms_projection_service.py").read_text(encoding="utf-8")

    assert "PmsProjectionRepo" in text
    assert "RESOURCE_CONFIGS" not in text
    assert "ProjectionResourceConfig" not in text
    assert "SELECT " not in text
    assert "INSERT INTO wms_pms_" not in text
    assert "UPDATE wms_pms_" not in text
    assert "DELETE FROM wms_pms_" not in text


def test_pms_projection_router_uses_pms_permissions_and_business_prefix() -> None:
    router_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "app/pms/projections/routers").glob("*.py"))
    )

    assert 'prefix="/projections"' in router_text
    assert "page.pms.read" in router_text
    assert "page.pms.write" in router_text

    for path in [
        '"/items"',
        '"/items/sync"',
        '"/items/check"',
        '"/suppliers"',
        '"/suppliers/sync"',
        '"/suppliers/check"',
        '"/uoms"',
        '"/uoms/sync"',
        '"/uoms/check"',
        '"/sku-codes"',
        '"/sku-codes/sync"',
        '"/sku-codes/check"',
        '"/barcodes"',
        '"/barcodes/sync"',
        '"/barcodes/check"',
    ]:
        assert path in router_text

    assert "{resource}" not in router_text
    assert "/admin" not in router_text
    assert "page.admin.read" not in router_text
    assert "page.admin.write" not in router_text
    assert "/connection" not in router_text


def test_pms_projection_router_is_not_mounted_under_admin() -> None:
    admin_router_path = ROOT / "app/admin/router.py"
    assert not admin_router_path.exists()
    admin_text = ""
    pms_text = (ROOT / "app/pms/router.py").read_text(encoding="utf-8")
    mount_text = (ROOT / "app/router_mount.py").read_text(encoding="utf-8")

    assert "pms_integration_router" not in admin_text
    assert "app.admin.routers.pms_integration" not in mount_text

    assert "pms_projection_router" in pms_text
    assert "router.include_router(pms_projection_router)" in pms_text
    assert "from app.pms.router import router as pms_router" in mount_text
    assert "app.include_router(pms_router)" in mount_text


def test_pms_projection_pages_are_rehomed_to_product_management_navigation() -> None:
    migration_text = "\n".join(
        path.read_text(encoding="utf-8")
        for pattern in (
            "*rehome_projection_pages.py",
            "*pms_projection_pages_level2.py",
        )
        for path in (ROOT / "alembic/versions").glob(pattern)
    )

    assert "pms.item_projection" in migration_text
    assert "pms.supplier_projection" in migration_text
    assert "pms.uom_projection" in migration_text
    assert "pms.sku_code_projection" in migration_text
    assert "pms.barcode_projection" in migration_text

    assert "/pms/item-projection" in migration_text
    assert "/pms/supplier-projection" in migration_text
    assert "/pms/uom-projection" in migration_text
    assert "/pms/sku-code-projection" in migration_text
    assert "/pms/barcode-projection" in migration_text

    assert "pms.projections" in migration_text
    assert "/pms/projections/items" in migration_text
    assert "admin.pms_integration.items" in migration_text
    assert "/admin/pms-integration/items" in migration_text
    assert "page.pms.read" in migration_text
    assert "page.pms.write" in migration_text
