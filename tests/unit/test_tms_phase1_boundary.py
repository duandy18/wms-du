# tests/unit/test_tms_phase1_boundary.py
from __future__ import annotations

from app.tms.phase1_boundary import (
    DomainOwner,
    TmsSubdomain,
    find_file_ownership,
    get_frozen_ownership,
)


def test_shipping_record_owned_by_transport_ledger() -> None:
    ownership = get_frozen_ownership("shipping_record")

    assert ownership.owner_domain == DomainOwner.TMS
    assert ownership.owner_subdomain == TmsSubdomain.TRANSPORT_LEDGER


def test_shipping_record_write_owned_by_transport_shipment() -> None:
    ownership = get_frozen_ownership("shipping_record_write")

    assert ownership.owner_domain == DomainOwner.TMS
    assert ownership.owner_subdomain == TmsSubdomain.TRANSPORT_SHIPMENT


def test_quote_owned_by_transport_quote() -> None:
    ownership = get_frozen_ownership("quote")

    assert ownership.owner_domain == DomainOwner.TMS
    assert ownership.owner_subdomain == TmsSubdomain.TRANSPORT_QUOTE


def test_order_owned_by_oms() -> None:
    ownership = get_frozen_ownership("order")

    assert ownership.owner_domain == DomainOwner.OMS
    assert ownership.owner_subdomain is None


def test_outbound_ship_confirm_is_frozen_as_transport_shipment() -> None:
    rule = find_file_ownership("app/api/routers/outbound_ship_routes_confirm.py")

    assert rule is not None
    assert rule.owner_domain == DomainOwner.TMS
    assert rule.owner_subdomain == TmsSubdomain.TRANSPORT_SHIPMENT


def test_ship_with_waybill_is_frozen_as_transport_shipment() -> None:
    rule = find_file_ownership("app/api/routers/orders_fulfillment_v2_routes_4_ship_with_waybill.py")

    assert rule is not None
    assert rule.owner_domain == DomainOwner.TMS
    assert rule.owner_subdomain == TmsSubdomain.TRANSPORT_SHIPMENT


def test_shipping_quote_service_cluster_is_frozen_as_transport_quote() -> None:
    rule = find_file_ownership("app/services/shipping_quote/recommend.py")

    assert rule is not None
    assert rule.owner_domain == DomainOwner.TMS
    assert rule.owner_subdomain == TmsSubdomain.TRANSPORT_QUOTE


def test_shipping_reports_routes_are_frozen_as_transport_reports() -> None:
    rule = find_file_ownership("app/api/routers/shipping_reports_routes_by_carrier.py")

    assert rule is not None
    assert rule.owner_domain == DomainOwner.TMS
    assert rule.owner_subdomain == TmsSubdomain.TRANSPORT_REPORTS


def test_unknown_path_returns_none() -> None:
    rule = find_file_ownership("app/services/not_related_domain.py")
    assert rule is None
