# tests/unit/test_tms_phase1_boundary.py
from __future__ import annotations

from app.tms.phase1_boundary import (
    DomainOwner,
    TmsSubdomain,
    find_file_ownership,
    get_frozen_ownership,
)


def test_shipping_record_owned_by_shipping_assist_records() -> None:
    ownership = get_frozen_ownership("shipping_record")

    assert ownership.owner_domain == DomainOwner.TMS
    assert ownership.owner_subdomain == TmsSubdomain.SHIPPING_ASSIST_RECORDS


def test_shipping_record_write_owned_by_shipping_assist_shipment() -> None:
    ownership = get_frozen_ownership("shipping_record_write")

    assert ownership.owner_domain == DomainOwner.TMS
    assert ownership.owner_subdomain == TmsSubdomain.SHIPPING_ASSIST_SHIPMENT


def test_quote_owned_by_shipping_assist_quote() -> None:
    ownership = get_frozen_ownership("quote")

    assert ownership.owner_domain == DomainOwner.TMS
    assert ownership.owner_subdomain == TmsSubdomain.SHIPPING_ASSIST_QUOTE


def test_order_owned_by_oms() -> None:
    ownership = get_frozen_ownership("order")

    assert ownership.owner_domain == DomainOwner.OMS
    assert ownership.owner_subdomain is None


def test_tms_quote_router_is_frozen_as_shipping_assist_quote() -> None:
    rule = find_file_ownership("app/tms/quote/router.py")

    assert rule is not None
    assert rule.owner_domain == DomainOwner.TMS
    assert rule.owner_subdomain == TmsSubdomain.SHIPPING_ASSIST_QUOTE


def test_tms_alerts_service_is_frozen_as_shipping_assist_quote() -> None:
    rule = find_file_ownership("app/tms/alerts/service.py")

    assert rule is not None
    assert rule.owner_domain == DomainOwner.TMS
    assert rule.owner_subdomain == TmsSubdomain.SHIPPING_ASSIST_QUOTE


def test_tms_waybill_service_is_frozen_as_shipping_assist_shipment() -> None:
    rule = find_file_ownership("app/tms/shipment/waybill_service.py")

    assert rule is not None
    assert rule.owner_domain == DomainOwner.TMS
    assert rule.owner_subdomain == TmsSubdomain.SHIPPING_ASSIST_SHIPMENT


def test_tms_shipment_calc_route_is_frozen_as_shipping_assist_shipment() -> None:
    rule = find_file_ownership("app/tms/shipment/routes_calc.py")

    assert rule is not None
    assert rule.owner_domain == DomainOwner.TMS
    assert rule.owner_subdomain == TmsSubdomain.SHIPPING_ASSIST_SHIPMENT


def test_tms_shipment_prepare_route_is_frozen_as_shipping_assist_shipment() -> None:
    rule = find_file_ownership("app/tms/shipment/routes_prepare.py")

    assert rule is not None
    assert rule.owner_domain == DomainOwner.TMS
    assert rule.owner_subdomain == TmsSubdomain.SHIPPING_ASSIST_SHIPMENT


def test_tms_shipment_router_is_frozen_as_shipping_assist_shipment() -> None:
    rule = find_file_ownership("app/tms/shipment/router.py")

    assert rule is not None
    assert rule.owner_domain == DomainOwner.TMS
    assert rule.owner_subdomain == TmsSubdomain.SHIPPING_ASSIST_SHIPMENT


def test_tms_orders_v2_shipment_router_is_frozen_as_shipping_assist_shipment() -> None:
    rule = find_file_ownership("app/tms/shipment/orders_v2_router.py")

    assert rule is not None
    assert rule.owner_domain == DomainOwner.TMS
    assert rule.owner_subdomain == TmsSubdomain.SHIPPING_ASSIST_SHIPMENT


def test_ship_with_waybill_is_frozen_as_shipping_assist_shipment() -> None:
    rule = find_file_ownership("app/tms/shipment/routes_ship_with_waybill.py")

    assert rule is not None
    assert rule.owner_domain == DomainOwner.TMS
    assert rule.owner_subdomain == TmsSubdomain.SHIPPING_ASSIST_SHIPMENT


def test_tms_records_router_is_frozen_as_shipping_assist_records() -> None:
    rule = find_file_ownership("app/tms/records/router.py")

    assert rule is not None
    assert rule.owner_domain == DomainOwner.TMS
    assert rule.owner_subdomain == TmsSubdomain.SHIPPING_ASSIST_RECORDS


def test_tms_reports_router_is_frozen_as_shipping_assist_reports() -> None:
    rule = find_file_ownership("app/tms/reports/router.py")

    assert rule is not None
    assert rule.owner_domain == DomainOwner.TMS
    assert rule.owner_subdomain == TmsSubdomain.SHIPPING_ASSIST_REPORTS


def test_shipping_reports_routes_are_frozen_as_shipping_assist_reports() -> None:
    rule = find_file_ownership("app/api/routers/shipping_reports_routes_by_carrier.py")

    assert rule is not None
    assert rule.owner_domain == DomainOwner.TMS
    assert rule.owner_subdomain == TmsSubdomain.SHIPPING_ASSIST_REPORTS


def test_deleted_legacy_shipping_quote_router_returns_none() -> None:
    rule = find_file_ownership("app/api/routers/shipping_quote.py")
    assert rule is None


def test_deleted_legacy_shipping_quote_recommend_route_returns_none() -> None:
    rule = find_file_ownership("app/api/routers/shipping_quote_routes_recommend.py")
    assert rule is None


def test_deleted_legacy_shipping_records_router_returns_none() -> None:
    rule = find_file_ownership("app/api/routers/shipping_records.py")
    assert rule is None


def test_deleted_legacy_shipping_reports_router_returns_none() -> None:
    rule = find_file_ownership("app/api/routers/shipping_reports.py")
    assert rule is None


def test_unknown_path_returns_none() -> None:
    rule = find_file_ownership("app/services/not_related_domain.py")
    assert rule is None
