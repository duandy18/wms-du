# app/router_mount.py
from __future__ import annotations

from fastapi import APIRouter, FastAPI


def mount_routers(app: FastAPI, *, enable_dev_routes: bool) -> None:
    # ---------------------------------------------------------------------------
    # routers imports
    # ---------------------------------------------------------------------------
    from app.api.routers.autoheal_execute import router as autoheal_execute_router
    from app.api.routers.count import router as count_router
    from app.api.routers.debug_trace import router as debug_trace_router
    from app.api.routers.dev_seed_ledger import router as dev_seed_ledger_router
    from app.api.routers.devconsole_orders import router as devconsole_orders_router
    from app.api.routers.fake_platform import router as fake_platform_router
    from app.api.routers.finance_overview import router as finance_overview_router
    from app.api.routers.flow_replay import router as flow_replay_router
    from app.api.routers.inbound_receipts import router as inbound_receipts_router
    from app.api.routers.inbound_receipts import po_receive_router as po_receive_router
    # ✅ 新增：收货单草稿（对照 PO 打勾 → 扫码/录入 → commit 生成 confirmed receipt）
    from app.api.routers.intelligence import router as intelligence_router
    from app.api.routers.item_barcodes import router as item_barcodes_router
    from app.api.routers.items import router as items_router
    from app.api.routers.ledger_reconcile_v2 import router as ledger_reconcile_v2_router
    from app.api.routers.ledger_timeline import router as ledger_timeline_router
    from app.api.routers.lifecycle import router as lifecycle_router
    from app.api.routers.metrics import router as metrics_router
    from app.api.routers.orders import router as orders_router
    from app.api.routers.orders_sla_stats import router as orders_sla_stats_router
    from app.api.routers.orders_stats import router as orders_stats_router
    from app.api.routers.outbound import router as outbound_router
    from app.api.routers.outbound_ops import router as outbound_ops_router
    from app.api.routers.outbound_ship import router as outbound_ship_router
    from app.api.routers.pdd_auth import router as pdd_auth_router
    from app.api.routers.permissions import router as permissions_router
    from app.api.routers.pick import router as pick_router
    from app.api.routers.pick_tasks import router as pick_tasks_router
    from app.api.routers.platform_orders_ingest import router as platform_orders_ingest_router
    from app.api.routers.platform_shops import router as platform_shops_router
    from app.api.routers.pricing_integrity_ops import router as pricing_integrity_ops_router
    from app.api.routers.print_jobs import router as print_jobs_router
    from app.api.routers.purchase_orders import router as purchase_orders_router
    from app.api.routers.purchase_reports import router as purchase_reports_router
    from app.api.routers.return_tasks import router as return_tasks_router
    from app.api.routers.roles import router as roles_router

    from app.api.routers.shipping_provider_contacts import router as shipping_provider_contacts_router
    from app.api.routers.shipping_provider_pricing_schemes.router import (
        router as shipping_provider_pricing_schemes_router,
    )
    from app.api.routers.shipping_providers import router as shipping_providers_router
    from app.api.routers.shipping_quote import router as shipping_quote_router
    from app.api.routers.shipping_records import router as shipping_records_router
    from app.api.routers.shipping_reports import router as shipping_reports_router
    from app.api.routers.snapshot import router as snapshot_router
    from app.api.routers.snapshot_v3 import router as snapshot_v3_router
    from app.api.routers.stock_batch import router as stock_batch_router
    from app.api.routers.stock_ledger import router as stock_ledger_router

    from app.api.routers.internal_outbound import router as internal_outbound_router

    from app.api.routers.meta import router as meta_router
    from app.api.routers.stores import router as stores_router
    from app.api.routers.suppliers import router as suppliers_router
    from app.api.routers.supplier_contacts import router as supplier_contacts_router

    from app.api.routers.user import router as user_router
    from app.api.routers.warehouses import router as warehouses_router

    from app.api.routers.geo_cn import router as geo_router

    from app.api.routers.orders_fulfillment_debug_routes import (
        router as orders_fulfillment_debug_router,
    )

    from app.api.routers.shop_product_bundles import router as shop_product_bundles_router

    # ✅ 新增：merchant_code(current) → published FSKU 绑定路由
    from app.api.routers.merchant_code_bindings import router as merchant_code_bindings_router

    # ✅ 新增：dev fake orders lab（仅 dev 路由开关启用时挂载）
    from app.api.routers.dev_fake_orders import router as dev_fake_orders_router

    # ---------------------------------------------------------------------------
    # scan routes
    # ---------------------------------------------------------------------------
    from app.api.routers import scan_routes_count_commit, scan_routes_entrypoint

    scan_router = APIRouter(tags=["scan"])
    scan_routes_entrypoint.register(scan_router)
    scan_routes_count_commit.register(scan_router)

    # ---------------------------------------------------------------------------
    # orders_fulfillment_v2 routes
    # ---------------------------------------------------------------------------
    from app.api.routers import (
        orders_fulfillment_v2_routes_1_reserve,
        orders_fulfillment_v2_routes_2_pick,
        orders_fulfillment_v2_routes_3_ship,
        orders_fulfillment_v2_routes_4_ship_with_waybill,
    )

    orders_fulfillment_v2_router = APIRouter(prefix="/orders", tags=["orders-fulfillment-v2"])
    orders_fulfillment_v2_routes_1_reserve.register(orders_fulfillment_v2_router)
    orders_fulfillment_v2_routes_2_pick.register(orders_fulfillment_v2_router)
    orders_fulfillment_v2_routes_3_ship.register(orders_fulfillment_v2_router)
    orders_fulfillment_v2_routes_4_ship_with_waybill.register(orders_fulfillment_v2_router)

    # ===========================
    # mount routers
    # ===========================
    app.include_router(scan_router)
    app.include_router(count_router)
    app.include_router(pick_router)

    app.include_router(platform_orders_ingest_router)
    app.include_router(merchant_code_bindings_router)

    app.include_router(orders_router)
    app.include_router(orders_fulfillment_v2_router)

    app.include_router(orders_fulfillment_debug_router)

    app.include_router(outbound_router)
    app.include_router(outbound_ship_router)
    app.include_router(internal_outbound_router)
    app.include_router(outbound_ops_router)

    app.include_router(purchase_orders_router)
    app.include_router(purchase_reports_router)
    app.include_router(inbound_receipts_router)
    app.include_router(po_receive_router)
    # ✅ 新增：草稿收货单（先勾选/扫码/录入 → commit 生成 confirmed receipt）
    app.include_router(return_tasks_router)
    app.include_router(pick_tasks_router)
    app.include_router(print_jobs_router)

    app.include_router(meta_router)
    app.include_router(stores_router)
    app.include_router(shop_product_bundles_router)

    app.include_router(warehouses_router)
    app.include_router(platform_shops_router)
    app.include_router(pdd_auth_router)
    app.include_router(items_router)
    app.include_router(item_barcodes_router)

    app.include_router(suppliers_router)
    app.include_router(supplier_contacts_router)

    app.include_router(shipping_providers_router)
    app.include_router(shipping_provider_contacts_router)
    app.include_router(shipping_provider_pricing_schemes_router)
    app.include_router(geo_router)
    app.include_router(pricing_integrity_ops_router)
    app.include_router(shipping_quote_router)
    app.include_router(shipping_reports_router)
    app.include_router(shipping_records_router)

    app.include_router(debug_trace_router)
    app.include_router(metrics_router)
    app.include_router(snapshot_router)

    app.include_router(stock_batch_router)
    app.include_router(stock_ledger_router)

    app.include_router(orders_stats_router)
    app.include_router(orders_sla_stats_router)

    app.include_router(user_router)
    app.include_router(roles_router)
    app.include_router(permissions_router)

    app.include_router(ledger_reconcile_v2_router)
    app.include_router(ledger_timeline_router)
    app.include_router(snapshot_v3_router)
    app.include_router(flow_replay_router)
    app.include_router(lifecycle_router)
    app.include_router(intelligence_router)
    app.include_router(autoheal_execute_router)

    app.include_router(finance_overview_router)

    if enable_dev_routes:
        app.include_router(devconsole_orders_router)
        app.include_router(dev_seed_ledger_router)
        app.include_router(fake_platform_router)
        app.include_router(dev_fake_orders_router)
