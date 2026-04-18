# app/router_mount.py
from __future__ import annotations

from fastapi import APIRouter, FastAPI


def mount_routers(app: FastAPI, *, enable_dev_routes: bool) -> None:
    # ---------------------------------------------------------------------------
    # routers imports
    # ---------------------------------------------------------------------------
    from app.admin.router import router as admin_router
    from app.diagnostics.routers.autoheal_execute import router as autoheal_execute_router
    from app.wms.count.routers.count import router as count_router
    from app.wms.reconciliation.routers.stock_inventory_recount import router as stock_inventory_recount_router
    from app.diagnostics.routers.debug_trace import router as debug_trace_router
    from app.devtools.routers.dev_seed_ledger import router as dev_seed_ledger_router
    from app.devtools.routers.dev_stock_adjust import router as dev_stock_adjust_router
    from app.devtools.routers.fake_platform_routes import router as fake_platform_router
    from app.analytics.routers.finance_overview import router as finance_overview_router
    from app.diagnostics.routers.flow_replay import router as flow_replay_router
    from app.tms.routers.geo_cn import router as geo_router
    from app.diagnostics.routers.intelligence import router as intelligence_router
    from app.pms.items.routers.item_aggregate import router as item_aggregate_router
    from app.pms.items.routers.item_barcodes import router as item_barcodes_router
    from app.pms.items.routers.item_uoms import router as item_uoms_router
    from app.pms.items.routers.items import router as items_router
    from app.pms.public.items.routers.barcode_probe import router as pms_public_barcode_probe_router
    from app.pms.public.items.routers.item_aggregate_read import (
        router as pms_public_item_aggregate_read_router,
    )
    from app.pms.public.items.routers.items_read import router as pms_public_items_read_router
    from app.pms.public.suppliers.routers.suppliers_read import (
        router as pms_public_suppliers_read_router,
    )
    from app.wms.analysis.routers.ledger_reconcile_v2 import router as ledger_reconcile_v2_router
    from app.wms.ledger.routers.ledger_timeline import router as ledger_timeline_router
    from app.diagnostics.routers.lifecycle import router as lifecycle_router
    from app.oms.routers.meta_platforms import router as meta_router
    from app.diagnostics.routers.metrics import router as metrics_router
    from app.wms.outbound.routers.orders_fulfillment_debug import (
        router as orders_fulfillment_debug_router,
    )
    from app.analytics.routers.orders_sla_stats_routes import router as orders_sla_stats_router
    from app.analytics.routers.orders_stats_routes import router as orders_stats_router
    from app.wms.inbound.routers.inbound_events import router as inbound_events_router
    from app.wms.inbound.routers.inbound_commit import router as inbound_commit_router
    from app.wms.outbound.routers.outbound import router as outbound_router
    from app.wms.outbound.routers.pick import router as pick_router
    from app.wms.outbound.routers.pick_tasks import router as pick_tasks_router
    from app.wms.outbound.routers.print_jobs import router as print_jobs_router
    from app.procurement.routers.purchase_orders import router as purchase_orders_router
    from app.procurement.routers.purchase_reports import router as purchase_reports_router
    from app.inbound_receipts.routers.inbound_receipts import router as inbound_receipts_router
    from app.wms.receiving.routers.inbound_operations import router as inbound_operations_router
    from app.wms.outbound.routers.return_tasks import router as return_tasks_router
    from app.wms.stock.routers.inventory import router as stock_inventory_router
    from app.wms.snapshot.routers.snapshot_v3 import router as snapshot_v3_router
    from app.wms.ledger.routers.stock_ledger import router as stock_ledger_router
    from app.pms.suppliers.routers.supplier_contacts import router as supplier_contacts_router
    from app.pms.suppliers.routers.suppliers import router as suppliers_router
    from app.user.routers.user import router as user_router
    from app.wms.warehouses.routers.warehouses import router as warehouses_router

    from app.devtools.routers.dev_fake_orders_routes import router as dev_fake_orders_router
    from app.wms.outbound.routers.internal_outbound import router as internal_outbound_router

    from app.oms.router import router as oms_router

    from app.tms.billing.router import router as tms_billing_router
    from app.tms.pricing.router import router as tms_pricing_router
    from app.tms.providers.router import router as tms_providers_router
    from app.tms.quote.router import router as tms_quote_router
    from app.tms.records.router import router as tms_records_router
    from app.tms.reports.router import router as tms_reports_router
    from app.tms.shipment.orders_v2_router import router as tms_orders_shipment_v2_router
    from app.tms.shipment.router import router as tms_shipment_router

    # ---------------------------------------------------------------------------
    # scan routes
    # ---------------------------------------------------------------------------
    from app.wms.scan.routers.scan_entrypoint import register as register_scan_entrypoint

    scan_router = APIRouter(tags=["scan"])
    register_scan_entrypoint(scan_router)

    # ---------------------------------------------------------------------------
    # orders_fulfillment_v2 routes
    # ---------------------------------------------------------------------------
    from app.wms.outbound.routers.orders_fulfillment_v2_routes_1_reserve import (
        register as register_orders_fulfillment_v2_reserve,
    )
    from app.wms.outbound.routers.orders_fulfillment_v2_routes_2_pick import (
        register as register_orders_fulfillment_v2_pick,
    )

    orders_fulfillment_v2_router = APIRouter(prefix="/orders", tags=["orders-fulfillment-v2"])
    register_orders_fulfillment_v2_reserve(orders_fulfillment_v2_router)
    register_orders_fulfillment_v2_pick(orders_fulfillment_v2_router)

    # ===========================
    # mount routers
    # ===========================
    app.include_router(scan_router)
    app.include_router(count_router)
    app.include_router(stock_inventory_recount_router)
    app.include_router(pick_router)

    app.include_router(orders_fulfillment_v2_router)
    app.include_router(tms_orders_shipment_v2_router)
    app.include_router(orders_fulfillment_debug_router)

    app.include_router(outbound_router)
    app.include_router(tms_shipment_router)
    app.include_router(internal_outbound_router)

    app.include_router(purchase_orders_router)
    app.include_router(purchase_reports_router)
    app.include_router(inbound_receipts_router)
    app.include_router(inbound_operations_router)
    app.include_router(inbound_events_router)
    app.include_router(inbound_commit_router)
    app.include_router(return_tasks_router)
    app.include_router(pick_tasks_router)
    app.include_router(print_jobs_router)

    app.include_router(meta_router)
    app.include_router(oms_router)

    app.include_router(warehouses_router)

    # PMS 相关：
    # - public 读面先挂
    # - /items/barcode-probe 先于 /items/{id}
    # - /items/aggregate 先于 /items/{id}
    # - /public/items、/public/suppliers 独立前缀，不与 owner 冲突
    app.include_router(pms_public_item_aggregate_read_router)
    app.include_router(pms_public_items_read_router)
    app.include_router(pms_public_barcode_probe_router)
    app.include_router(pms_public_suppliers_read_router)
    app.include_router(item_aggregate_router)
    app.include_router(items_router)
    app.include_router(item_barcodes_router)
    app.include_router(item_uoms_router)

    app.include_router(suppliers_router)
    app.include_router(supplier_contacts_router)

    app.include_router(tms_providers_router)
    app.include_router(geo_router)

    app.include_router(tms_quote_router)
    app.include_router(tms_pricing_router)

    app.include_router(tms_reports_router)
    app.include_router(tms_records_router)
    app.include_router(tms_billing_router)

    app.include_router(debug_trace_router)
    app.include_router(metrics_router)
    app.include_router(stock_inventory_router)

    app.include_router(stock_ledger_router)

    app.include_router(orders_stats_router)
    app.include_router(orders_sla_stats_router)

    app.include_router(user_router)
    app.include_router(admin_router)

    app.include_router(ledger_reconcile_v2_router)
    app.include_router(ledger_timeline_router)
    app.include_router(snapshot_v3_router)
    app.include_router(flow_replay_router)
    app.include_router(lifecycle_router)
    app.include_router(intelligence_router)
    app.include_router(autoheal_execute_router)

    app.include_router(finance_overview_router)

    if enable_dev_routes:
        app.include_router(dev_seed_ledger_router)
        app.include_router(dev_stock_adjust_router)
        app.include_router(fake_platform_router)
        app.include_router(dev_fake_orders_router)
