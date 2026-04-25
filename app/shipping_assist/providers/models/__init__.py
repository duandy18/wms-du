# app/shipping_assist/providers/models/__init__.py
# Domain-owned ORM models for TMS providers, waybill configs, and warehouse-provider bindings.

from app.shipping_assist.providers.models.electronic_waybill_config import ElectronicWaybillConfig
from app.shipping_assist.providers.models.shipping_provider import ShippingProvider
from app.shipping_assist.providers.models.shipping_provider_contact import ShippingProviderContact
from app.shipping_assist.providers.models.warehouse_shipping_provider import WarehouseShippingProvider

__all__ = [
    "ElectronicWaybillConfig",
    "ShippingProvider",
    "ShippingProviderContact",
    "WarehouseShippingProvider",
]
